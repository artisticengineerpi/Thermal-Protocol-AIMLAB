"""Drive the complete UI state machine without a window or hardware."""
from types import SimpleNamespace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from aimlab.ui import ExperimentApp
from aimlab.protocol import Settings, sequence
from aimlab.storage import Session


class FakeLink:
    def __init__(self):
        self.state = {"state": "READY", "fault_count": 0, "generation": 1, "detail": "Test double"}
        self.runs = []
        self.stops = 0

    def snapshot(self):
        return self.state.copy()

    def run(self, condition, settings):
        self.runs.append((condition, settings))
        return SimpleNamespace(id="test-ticket", sent=1., ack=1.01, done_received=5.,
                               finished=5.01, error="")

    def stop(self):
        self.stops += 1


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = app = ExperimentApp.__new__(ExperimentApp)
        app.config = {"response_delay_s": 1.}
        app.session = Session.create(tmp.name, "TEST", {}, sequence(4), 4)
        app.settings = Settings()
        app.connector = FakeLink()
        app.win = SimpleNamespace(nDroppedFrames=0)
        app.smoke = False
        app.text = lambda *args, **kwargs: None
        app.ticket = app.attempt = None
        app.tone500 = app.tone1000 = None
        app.phase = "instructions"
        app.phase_onset = time.monotonic()
        app.flip_pending = None
        app.resume_target = None
        app.break_duration = 60
        app.note = ""

    def step(self, keys=(), elapsed=0):
        self.app.phase_onset = time.monotonic()-elapsed
        self.app.experiment(self.app.snapshot(), keys)

    def one_trial(self):
        app = self.app
        if app.phase != "fixation":
            app.begin_attempt()
        self.assertEqual(app.phase, "fixation")
        self.step(elapsed=5)
        self.assertEqual(app.phase, "stim")
        app.phase_flip()
        self.assertIsNotNone(app.ticket)
        self.step(elapsed=6)
        self.assertEqual(app.phase, "response_delay")
        self.step(elapsed=1.1)
        self.assertEqual(app.phase, "response")
        self.step(keys=[("4", .7)], elapsed=.7)

    def test_all_160_responses_and_four_breaks(self):
        app = self.app
        breaks = 0
        for index in range(160):
            self.one_trial()
            self.assertEqual(app.session.state["next_index"], index+1)
            if app.phase == "break":
                breaks += 1
                self.step(keys=[("space", 0)], elapsed=10)
                self.assertEqual(app.phase, "break")
                self.step(keys=[("space", 0)], elapsed=61)
                self.assertEqual(app.phase, "fixation")
        self.assertEqual(app.phase, "complete")
        self.assertEqual(breaks, 4)
        self.assertEqual(len(app.connector.runs), 160)
        self.assertTrue(all(settings.thermal_pwm == 183 and settings.motion_ms == 4000
                            for _,settings in app.connector.runs))

    def test_link_loss_invalidates_trial_and_space_repeats_same_index(self):
        app = self.app
        app.begin_attempt()
        app.connector.state.update(state="DISCONNECTED", fault_count=1)
        self.step()
        self.assertEqual(app.phase, "paused")
        self.assertEqual(app.session.state["next_index"], 0)
        self.step(keys=[("space", 0)])
        self.assertEqual(app.phase, "paused")
        app.connector.state.update(state="READY", generation=2)
        self.step(keys=[("space", 0)])
        self.assertEqual(app.phase, "fixation")
        self.assertEqual(app.attempt["index"], 0)

    def test_response_not_accepted_before_options_flip(self):
        app = self.app
        app.begin_attempt()
        app.enter("response")
        app.experiment(app.snapshot(), [("1", .2)])
        self.assertEqual(app.session.state["next_index"], 0)

    def test_link_loss_between_trials_pauses_before_next_attempt(self):
        app = self.app
        app.phase = "response"
        app.connector.state["state"] = "DISCONNECTED"
        app.begin_attempt()
        self.assertEqual(app.phase, "paused")
        self.assertIsNone(app.attempt)
        self.assertEqual(app.session.state["next_index"], 0)

    def test_escape_then_q_stops_and_quits(self):
        app = self.app
        app.quit_requested = False
        app.begin_attempt()
        app.phase = "response"
        remaining = app.handle_controls([("escape", .5), ("4", .5), ("space", .5)])
        self.assertEqual(remaining, [])
        self.assertEqual(app.phase, "paused")
        self.assertEqual(app.session.state["next_index"], 0)
        self.assertIsNone(app.attempt)
        app.handle_controls([("q", .6)])
        self.assertTrue(app.quit_requested)
        self.assertGreater(app.connector.stops, 0)

    def test_dot_draws_everywhere_without_stop_button(self):
        app = self.app
        app.clicked = False
        app.rect = lambda *a, **kw: None
        app.experiment = lambda *a: None
        app.calibration = lambda *a: None
        for phase in ("calibration", "instructions", "fixation", "stim", "response_delay",
                      "response", "break", "paused", "complete"):
            calls = []
            app.phase = phase
            app.button = lambda key, *a, **kw: calls.append(key) or False
            app.draw_connection_indicator = lambda: calls.append("dot")
            app.draw([])
            self.assertEqual(calls, ["dot"], phase)


if __name__ == "__main__":
    unittest.main()
