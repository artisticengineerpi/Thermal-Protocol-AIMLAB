import json
from pathlib import Path
import tempfile
import unittest
from aimlab.storage import Session
from aimlab.protocol import sequence, Settings


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.session = Session.create(self.tmp.name, "P7", {}, sequence(2), 2)

    def test_abort_does_not_advance_and_resume_recovers_response(self):
        s = self.session
        s.finish_attempt({"attempt_id": "one", "index": 0, "status": "aborted"})
        self.assertEqual(s.state["next_index"], 0)
        s.finish_attempt({"attempt_id": "two", "index": 0, "status": "complete", "response": 4})
        s.state["next_index"] = 0
        s.save()  # simulate stale checkpoint after committed response
        resumed = Session(s.folder)
        self.assertEqual(resumed.state["next_index"], 1)
        self.assertIn("complete", (s.folder / "trials.csv").read_text())

    def test_interrupted_attempt_is_recorded_and_torn_tail_preserved(self):
        s = self.session
        s.state["active_attempt"] = {"attempt_id": "crash", "index": 0}
        s.save()
        (s.folder / "attempts.jsonl").write_bytes(b'{"attempt_id":')
        resumed = Session(s.folder)
        self.assertEqual(resumed.state["next_index"], 0)
        record = json.loads((s.folder / "attempts.jsonl").read_text())
        self.assertEqual(record["status"], "aborted")
        self.assertTrue(list(s.folder.glob("torn-record-*.bin")))

    def test_calibration_persists_and_session_names_are_safe(self):
        self.session.calibrate(Settings(128, 980), lock=True)
        resumed = Session(self.session.folder)
        self.assertTrue(resumed.state["calibration_locked"])
        self.assertEqual(resumed.state["calibration"]["motor_pwm"], 128)
        with self.assertRaises(ValueError):
            Session.create(self.tmp.name, "../bad", {}, sequence(1), 1)


if __name__ == "__main__":
    unittest.main()
