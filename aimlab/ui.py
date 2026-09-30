"""Native PsychoPy display, calibration controls and recoverable trial state machine."""
import json
from pathlib import Path
import queue
import time
import uuid

from psychopy import visual, core, event, sound
from .connector import UnoConnector
from .status import connection_is_fresh
from .protocol import Settings, CONDITIONS, RESPONSES
from .storage import atomic_json, utc_now

INK = "#FFFFFF"
BACKGROUND = "#000000"
TEAL = "#258A80"
RED = "#C64B43"
ORANGE = "#CE6943"
PURPLE = "#7966AD"


class ExperimentApp:
    def __init__(self, root, config, session, smoke=False):
        self.root, self.config, self.session, self.smoke = Path(root), config, session, smoke
        self.win = visual.Window(size=(1280, 800), units="norm", color=BACKGROUND,
                                 fullscr=config["fullscreen"] and not smoke,
                                 screen=config["screen"], allowGUI=True, waitBlanking=True,
                                 checkTiming=False, useFBO=True)
        self.win.recordFrameIntervals = True
        self.mouse = event.Mouse(win=self.win)
        self.connection_dot = visual.Circle(self.win, radius=.010, units="height",
            pos=(self.win.size[0]/self.win.size[1]/2-.035, .46),
            fillColor="#EF4444", lineColor="#EF4444", autoLog=False)
        self.was_down = False
        self.clicked = False
        self.texts, self.rects = {}, {}
        self.text_specs = {}
        self.rect_specs = {}
        self.phase = "calibration"
        self.phase_onset = time.monotonic()
        self.flip_pending = None
        self.response_clock = core.Clock()
        self.quit_requested = False
        self.note = "Choose motor intensity and lead, then try a sensation."
        self.ticket = None
        self.attempt = None
        self.attempt_fault = 0
        self.attempt_generation = 0
        self.frame_baseline = 0
        self.resume_target = None
        self.break_duration = config["break_s"]
        self.settings = Settings(config["initial_motor_pwm"], config["initial_lead_ms"],
                                 config["thermal_pwm"], config["motion_ms"], config["polarity"])
        if session and session.state["calibration"]:
            self.settings = Settings(**session.state["calibration"])
        if session and session.state["calibration_locked"]:
            self.phase = "paused"
            self.note = "Session recovered. Outputs must be OFF before continuing."
            self.resume_target = "trial"
            if session.state["next_index"] and session.state["next_index"] % 32 == 0:
                self.resume_target = "break"
        if session and session.state["status"] == "complete":
            self.phase = "complete"
        self.presets_path = self.root / "calibration" / "presets.json"
        self.presets = json.loads(self.presets_path.read_text(encoding="utf-8"))
        self.preset_index = 0
        self.connector = None if smoke else UnoConnector(config.get("preferred_port"))
        self.tone500 = self.tone1000 = None
        self.cue_test_at = None
        # Preview checks draw only. Real sessions fail visibly if cue audio cannot initialize.
        if not smoke:
            try:
                from psychopy.hardware.speaker import SpeakerDevice
                outputs = [d["deviceName"] for d in SpeakerDevice.getAvailableDevices()]
                if config.get("audio_device") not in outputs:
                    raise RuntimeError("Selected audio output is unavailable: " + str(config.get("audio_device")))
                self.speaker = SpeakerDevice(config["audio_device"])
                self.tone500 = sound.Sound(value=500, secs=config["tone_duration_s"], volume=.35, speaker=self.speaker)
                self.tone1000 = sound.Sound(value=1000, secs=config["tone_duration_s"], volume=.35, speaker=self.speaker)
            except Exception as exc:
                self.win.close()
                raise RuntimeError("Audio cues could not initialize: " + str(exc)) from exc

    def log(self, kind, **values):
        if self.session:
            self.session.event(kind, **values)

    def text(self, key, value, x, y, size=.043, color=INK, align="center", width=1.8):
        color = INK  # All display text, including fixation and status, is white.
        if key not in self.texts:
            self.texts[key] = visual.TextStim(self.win, text=value, pos=(x, y), height=size,
                                            color=color, alignText=align, anchorHoriz=align,
                                            wrapWidth=width, font="Arial", autoLog=False)
        obj = self.texts[key]
        # Rebuilding font geometry every frame is expensive on some GPUs.
        if obj.text != value:
            obj.text = value
        previous = self.text_specs.get(key)
        if previous != (x, y, size, color):
            obj.pos, obj.height, obj.color = (x, y), size, color
            self.text_specs[key] = (x, y, size, color)
        obj.draw()

    def rect(self, key, x, y, w, h, color="white", border="#CCD6DE"):
        if key not in self.rects:
            self.rects[key] = visual.Rect(self.win, width=w, height=h, pos=(x,y),
                                          fillColor=color, lineColor=border, autoLog=False)
        obj = self.rects[key]
        spec = (x,y,w,h,color,border)
        if self.rect_specs.get(key) != spec:
            obj.pos, obj.width, obj.height = (x,y), max(.001,w), h
            obj.fillColor, obj.lineColor = color, border
            self.rect_specs[key] = spec
        obj.draw()
        return obj

    def button(self, key, label, x, y, w=.36, color=TEAL, enabled=True, h=.105):
        obj = self.rect(key, x, y, w, h, BACKGROUND, INK if enabled else "#444444")
        self.text(key+"_label", label, x, y, .034, "white" if enabled else "#758392", width=w-.02)
        return enabled and self.clicked and obj.contains(self.mouse)

    def slider(self, key, label, value, low, high, step, x, y, enabled=True, unit=""):
        w = .75
        self.text(key+"_label", label, x-w/2, y+.1, .039, align="left", width=w)
        self.text(key+"_value", str(value)+unit, x+w/2, y+.1, .039, color=TEAL, align="right")
        track = self.rect(key+"_hit", x, y, w, .075, BACKGROUND, BACKGROUND)
        if enabled and self.mouse.getPressed()[0] and track.contains(self.mouse):
            fraction = min(1, max(0, (self.mouse.getPos()[0] - (x-w/2))/w))
            value = int(round((low+fraction*(high-low))/step)*step)
        self.rect(key+"_track", x, y, w, .012, "#666666", "#666666")
        marker = x-w/2+w*(value-low)/(high-low)
        self.rect(key+"_knob", marker, y, .028, .055, INK if enabled else "#666666", INK)
        self.text(key+"_low", f"{low}{unit}", x-w/2, y-.075, .026, "#6D7D8D", align="left")
        self.text(key+"_high", f"{high}{unit}", x+w/2, y-.075, .026, "#6D7D8D", align="right")
        return value

    def snapshot(self):
        if self.smoke:
            return {"state": "PREVIEW", "detail": "UI preview - no hardware connection",
                    "telemetry": None, "status_at": 0, "generation": 0, "fault_count": 0}
        return self.connector.snapshot()

    def enter(self, phase, on_flip=None):
        self.phase = phase
        self.flip_pending = on_flip or (lambda: None)
        self.phase_onset = float("inf")

    def phase_flip(self):
        self.phase_onset = time.monotonic()
        phase, onset = self.phase, self.phase_onset
        callback, self.flip_pending = self.flip_pending, None
        if callback:
            callback()
        self.log("display_flip", phase=phase, flip_monotonic=onset)

    def play(self, tone):
        if tone:
            tone.play()

    def save_calibration(self):
        self.session.calibrate(self.settings)
        entry = {"name": self.session.state["participant"] + " " + utc_now()[:19],
                 "motor_pwm": self.settings.motor_pwm, "lead_ms": self.settings.lead_ms}
        self.presets.append(entry)
        atomic_json(self.presets_path, self.presets)
        self.preset_index = len(self.presets)-1
        self.note = "Calibration saved to disk."

    def test(self, condition):
        try:
            self.ticket = self.connector.run(condition, self.settings)
            self.log("calibration_test", condition=condition, settings=self.settings.to_dict(), ticket=self.ticket.id)
            self.note = "Testing " + CONDITIONS.get(condition, "M" + str(ord(condition)-ord("E")+1))
        except RuntimeError as exc:
            self.note = str(exc)

    def calibration(self, snapshot, keys):
        ready = snapshot["state"] == "READY" and self.ticket is None
        editable = self.ticket is None and (not self.session or not self.session.state["calibration_locked"])
        self.text("title", "AIMLAB\nSleeve calibration", 0, .925, .034, width=.6)
        self.text("fixed", f"Fixed: HOT {self.settings.thermal_pwm} PWM  |  Motor motion {self.settings.motion_ms/1000:.1f} s  |  SOA {self.settings.motion_ms//5} ms", 0, .75, .04)
        telemetry = snapshot["telemetry"]
        stale = time.monotonic()-snapshot["status_at"] > .65
        values = [None]*5 if telemetry is None or stale else [telemetry["motors"][0], telemetry["motors"][1],
                         telemetry["thermal"], telemetry["motors"][2], telemetry["motors"][3]]
        for i, (label, x, pin, test) in enumerate(zip(["M1", "M2", "Peltier", "M3", "M4"],
                     [-.72, -.36, 0, .36, .72], ["D5", "D6", "D9", "D3", "D11"], ["E", "F", None, "G", "H"])):
            self.rect("card"+str(i), x, .5, .31, .27, BACKGROUND, INK)
            self.text("device"+str(i), label+"  "+pin, x, .57, .041)
            self.text("pwm"+str(i), "—" if values[i] is None else f"{values[i]} / 255", x, .47, .046)
            fraction = (values[i] or 0)/255
            self.rect("bar_bg"+str(i), x, .395, .26, .012, "#444444")
            if fraction:
                self.rect("bar"+str(i), x-.13+.13*fraction, .395, .26*fraction, .012, INK)
            if test and self.button("test"+test, "Test "+label, x, .28, .29, enabled=ready, h=.085):
                self.test(test)
        self.text("monitor_note", "Uno-reported PWM outputs · temperature and physical vibration are not measured", 0, .17, .028, "#687A89")
        motor = self.slider("motor", "Motor intensity", self.settings.motor_pwm, 0, 255, 1, -.46, -.025, editable)
        lead = self.slider("lead", "Peltier lead", self.settings.lead_ms, 0, 2000, 10, .46, -.025, editable, " ms")
        if (motor, lead) != (self.settings.motor_pwm, self.settings.lead_ms):
            self.settings = Settings(motor, lead, self.config["thermal_pwm"], self.config["motion_ms"])
        preset = self.presets[self.preset_index]
        if self.button("prev", "<", -.88, -.22, .09, enabled=editable):
            self.preset_index = (self.preset_index-1)%len(self.presets)
        if self.button("next", ">", -.08, -.22, .09, enabled=editable):
            self.preset_index = (self.preset_index+1)%len(self.presets)
        self.text("preset", preset["name"], -.48, -.22, .032, width=.65)
        if self.button("load", "Load", .15, -.22, .27, enabled=editable):
            self.settings = Settings(preset["motor_pwm"], preset["lead_ms"], self.config["thermal_pwm"], self.config["motion_ms"])
            self.note = f"Loaded motor / lead only; HOT {self.settings.thermal_pwm} and {self.settings.motion_ms/1000:.1f} s stay fixed."
        if self.button("save", "Save calibration", .63, -.22, .52, enabled=editable and not self.smoke):
            self.save_calibration()
        for cond, x, color in zip("ABCD", [-.69,-.23,.23,.69], ["#63768C", ORANGE, TEAL, PURPLE]):
            if self.button("condition"+cond, CONDITIONS[cond], x, -.43, .42, color, ready):
                self.test(cond)
        self.text("note", self.note, 0, -.57, .033, width=1.8)
        self.text("setup_note", "Support the arm and hand on an insulating armrest; avoid direct contact with a cold tabletop.", 0, -.66, .027, "#687A89")
        if self.button("begin", "Lock calibration & start", .54, -.79, .72, enabled=ready):
            self.session.calibrate(self.settings, lock=True)
            self.session.state["status"] = "running"
            self.session.save()
            self.enter("instructions")
        if self.button("cues", "Test cues", -.08, -.79, .42, "#63768C", not self.smoke and self.ticket is None):
            self.play(self.tone500)
            self.cue_test_at = time.monotonic()+.35
            self.note = "Cue output: " + self.config["audio_device"]

    def begin_attempt(self):
        index = self.session.state["next_index"]
        if index >= len(self.session.state["trials"]):
            self.session.state["status"] = "complete"
            self.session.save()
            self.enter("complete")
            return
        trial = self.session.state["trials"][index]
        snapshot = self.snapshot()
        if snapshot["state"] != "READY":
            self.note = "Waiting for a connected Uno with outputs OFF."
            self.resume_target = "trial"
            self.enter("paused")
            return
        self.attempt = {**trial, **self.settings.to_dict(), "attempt_id": uuid.uuid4().hex,
                        "started_utc": utc_now(), "generation": snapshot["generation"]}
        self.session.state["active_attempt"] = self.attempt.copy()
        self.session.save()
        self.log("attempt_begin", **self.attempt)
        self.attempt_fault = snapshot["fault_count"]
        self.attempt_generation = snapshot["generation"]
        self.frame_baseline = self.win.nDroppedFrames
        self.enter("fixation", lambda: self.play(self.tone500))

    def send_run(self):
        try:
            self.ticket = self.connector.run(self.attempt["condition"], self.settings)
            self.play(self.tone1000)
        except RuntimeError as exc:
            self.abort(str(exc))

    def finish_attempt(self, status, reason="", response=None, rt=None):
        if not self.attempt:
            return
        record = {**self.attempt, "status": status, "reason": reason, "response": response,
                  "response_label": RESPONSES.get(response, ""), "rt_s": rt,
                  "finished_utc": utc_now(), "dropped_frames": self.win.nDroppedFrames-self.frame_baseline}
        if self.ticket:
            record.update(run_sent_monotonic=self.ticket.sent, ack_monotonic=self.ticket.ack,
                          done_monotonic=self.ticket.done_received)
        self.session.finish_attempt(record)
        self.session.state.pop("active_attempt", None)
        self.session.save()
        self.attempt = self.ticket = None

    def abort(self, reason):
        self.connector.stop()
        self.finish_attempt("aborted", reason)
        self.note = reason + "\nThis trial was not counted. Space repeats it after reconnection."
        self.resume_target = "trial"
        self.enter("paused")

    def stop(self, reason):
        self.connector.stop()
        self.cue_test_at = None
        for tone in (self.tone500, self.tone1000):
            if tone:
                tone.stop()
        if self.phase == "calibration":
            self.note = "Stopping all outputs."
        elif self.attempt:
            self.abort(reason)
        elif self.phase not in ("complete", "paused"):
            self.resume_target = "break" if self.phase == "break" else "trial"
            self.note = reason
            self.enter("paused")

    def response_flip(self):
        event.clearEvents(eventType="keyboard")
        self.response_clock.reset()

    def experiment(self, snapshot, keys):
        if self.attempt and (snapshot["fault_count"] != self.attempt_fault or
                             snapshot["generation"] != self.attempt_generation):
            self.abort("Uno connection interrupted")
        if self.attempt and self.ticket and self.ticket.error:
            self.abort(self.ticket.error)
        elapsed = time.monotonic()-self.phase_onset
        pressed = [key for key, stamp in keys]
        if self.phase == "instructions":
            self.text("welcome", "Ready", 0, .48, .09)
            self.text("instructions", "Rest your supported arm. Keep still and watch the screen.\n\nAfter each trial, choose what you felt:\n\n1  No sensation     2  Static thermal\n3  Moving vibration     4  Moving thermal\n5  Not sure", 0, .02, .048)
            self.text("instruction_start", "Space to begin", 0, -.67, .043)
            if "space" in pressed and snapshot["state"] == "READY":
                self.begin_attempt()
        elif self.phase == "fixation":
            self.text("fixation", "+", 0, 0, .42)
            if elapsed >= self.attempt["fixation_s"]:
                self.enter("stim", self.send_run)
        elif self.phase == "stim":
            # A blank participant display during stimulation, including preheat.
            if self.ticket and self.ticket.finished:
                self.enter("response_delay", lambda: self.play(self.tone500))
        elif self.phase == "response_delay":
            self.text("question", "Which sensation did you experience?", 0, .25, .055)
            if elapsed >= self.config["response_delay_s"]:
                self.enter("response", self.response_flip)
        elif self.phase == "response":
            self.text("question", "Which sensation did you experience?", 0, .58, .055)
            for i, label in RESPONSES.items():
                self.text("response"+str(i), f"{i}     {label}", -.42, .35-(i-1)*.17, .052, align="left")
            self.text("response_hint", "Use keys 1–5 or the numeric keypad", 0, -.63, .035, "#687A89")
            for key, stamp in keys:
                normalized = key.removeprefix("num_").removeprefix("num")
                if normalized in ("1","2","3","4","5") and elapsed >= 0 and stamp >= 0:
                    self.finish_attempt("complete", response=int(normalized), rt=stamp)
                    index = self.session.state["next_index"]
                    if index >= len(self.session.state["trials"]):
                        self.session.state["status"] = "complete"
                        self.session.save()
                        self.enter("complete")
                    elif index % 32 == 0:
                        self.enter("break")
                    else:
                        self.begin_attempt()
                    break
        elif self.phase == "break":
            remaining = max(0, self.break_duration-elapsed)
            self.text("break", "Take a break", 0, .3, .09)
            self.text("break_time", f"{remaining:.0f} seconds" if remaining else "Space to continue", 0, 0, .065)
            self.text("block", f"Completed {self.session.state['next_index']} of 160 trials", 0, -.28, .04)
            if not remaining and "space" in pressed and snapshot["state"] == "READY":
                self.begin_attempt()
        elif self.phase == "paused":
            self.text("paused", "Paused · outputs stopped", 0, .5, .065, RED)
            self.text("reason", self.note, 0, .14, .044, width=1.65)
            self.text("link", snapshot["state"]+"\n"+snapshot["detail"], 0, -.25, .033)
            self.text("resume", "Space to continue when connected", 0, -.65, .04)
            if "space" in pressed and snapshot["state"] == "READY":
                if self.resume_target == "break":
                    self.enter("break")
                else:
                    self.begin_attempt()
        elif self.phase == "complete":
            self.text("complete", "Thank you", 0, .3, .1)
            self.text("complete_detail", "All 160 responses are saved.", 0, -.08, .05)

    def draw(self, keys):
        # A transition must draw its NEW phase before the associated flip/cue.
        for _ in range(4):
            phase = self.phase
            snapshot = self.snapshot()
            if self.phase == "calibration":
                if self.ticket and (self.ticket.error or self.ticket.finished):
                    self.note = self.ticket.error or "Test complete; outputs OFF."
                    self.ticket = None
                self.calibration(snapshot, keys)
            else:
                self.experiment(snapshot, keys)
            if phase == self.phase:
                break
            self.win.clearBuffer()
            keys = []
        self.draw_connection_indicator()

    def draw_connection_indicator(self):
        color = "#22C55E" if connection_is_fresh(self.snapshot(), time.monotonic()) else "#EF4444"
        self.connection_dot.fillColor = self.connection_dot.lineColor = color
        self.connection_dot.draw()

    def handle_controls(self, keys):
        names = [key for key, stamp in keys]
        if "escape" in names:
            self.stop("Stopped by operator")
            keys = []
        if "q" in names and self.phase in ("calibration", "paused", "complete"):
            self.quit_requested = True
        return keys

    def run(self):
        # Compile the participant display text before powering the sleeve.
        self.text("fixation", "+", 0, 0, .42)
        self.text("question", "Which sensation did you experience?", 0, .58, .055)
        for i, label in RESPONSES.items():
            self.text("response"+str(i), f"{i}     {label}", -.42, .35-(i-1)*.17, .052, align="left")
        self.win.clearBuffer()
        self.connector.start()
        self.log("application_started", settings=self.settings.to_dict(), firmware_required="AIMLAB_COMBINED_V7",
                 audio_device=self.config.get("audio_device"))
        try:
            while not self.quit_requested:
                self.connector.pulse()
                if self.cue_test_at and time.monotonic() >= self.cue_test_at:
                    self.play(self.tone1000)
                    self.cue_test_at = None
                    self.log("audio_cue_test", device=self.config["audio_device"])
                # Drain bounded work per frame; keep serial I/O away from rendering.
                for _ in range(150):
                    try:
                        item = self.connector.events.get_nowait()
                    except queue.Empty:
                        break
                    kind = item.pop("kind")
                    item["worker_monotonic"] = item.pop("monotonic")
                    self.log(kind, **item)
                keys = event.getKeys(timeStamped=self.response_clock)
                names = [key for key, stamp in keys]
                keys = self.handle_controls(keys)
                if self.quit_requested:
                    continue
                down = self.mouse.getPressed()[0]
                self.clicked = down and not self.was_down and "escape" not in names
                self.was_down = down
                self.draw(keys)
                if self.flip_pending is not None:
                    self.win.callOnFlip(self.phase_flip)
                self.win.flip()
        except Exception as exc:
            self.connector.stop()
            self.finish_attempt("aborted", "Application exception: " + str(exc))
            self.log("application_error", error=str(exc))
            raise
        finally:
            self.connector.close()
            if self.attempt:
                self.finish_attempt("aborted", "Application closed")
            self.log("application_closed")
            self.win.close()

    def smoke_test(self):
        folder = self.root / "validation"
        folder.mkdir(exist_ok=True)
        try:
            for _ in range(30):
                self.draw([])
                self.win.flip()
            self.win.getMovieFrame(buffer="front")
            self.win.saveMovieFrames(str(folder / "calibration-preview.png"))
            self.phase = "response"
            self.phase_onset = time.monotonic()
            for _ in range(30):
                self.draw([])
                self.win.flip()
            self.win.getMovieFrame(buffer="front")
            self.win.saveMovieFrames(str(folder / "response-preview.png"))
            self.win.clearBuffer()
            self.text("fixation", "+", 0, 0, .42)
            self.draw_connection_indicator()
            self.win.flip()
            self.win.getMovieFrame(buffer="front")
            self.win.saveMovieFrames(str(folder / "fixation-preview.png"))
            print("Rendered black/white calibration, response and fixation previews. No serial ports opened.")
        finally:
            self.win.close()
