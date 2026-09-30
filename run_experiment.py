"""Launch with the installed standalone PsychoPy Python (see Launch PsychoPy.bat)."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="AIMLAB single-Uno PsychoPy study")
    parser.add_argument("--participant")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--port", help="Optional COM port; firmware identity still verified")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--screen", type=int)
    parser.add_argument("--audio", help="Exact PsychoPy audio output device name")
    parser.add_argument("--check", action="store_true", help="Validate environment without opening serial ports")
    parser.add_argument("--smoke-test", action="store_true", help="Render UI to PNG, no serial ports or stimulation")
    args = parser.parse_args()
    from aimlab.protocol import validate_study, sequence
    config = json.loads((ROOT / "study.json").read_text(encoding="utf-8"))
    validate_study(config)
    if args.check:
        import psychopy
        from psychopy import visual, core, event, sound
        import serial
        print("PsychoPy", psychopy.__version__, "| pyserial", serial.__version__)
        print("Study valid: HOT PWM", config["thermal_pwm"], "| motion", config["motion_ms"], "ms")
        print("Latin square: ABDC / BCAD / CDBA / DACB; 160 trials")
        print("No serial port opened; no outputs activated.")
        return
    from psychopy import gui
    from aimlab.storage import Session
    from aimlab.ui import ExperimentApp
    if args.smoke_test:
        app = ExperimentApp(ROOT, config, session=None, smoke=True)
        app.smoke_test()
        return
    if args.resume:
        session = Session(args.resume.resolve())
        config = session.state["config"]
        validate_study(config)
    else:
        if not args.participant:
            from psychopy.hardware.speaker import SpeakerDevice
            outputs = [d["deviceName"] for d in SpeakerDevice.getAvailableDevices()]
            if not outputs:
                raise RuntimeError("No audio output found for experiment cues")
            preferred = args.audio or config.get("audio_device")
            outputs.sort(key=lambda name: name != preferred)
            setup = {"Participant ID": "P01", "Seed (fixation only)": str(args.seed),
                     "Fullscreen": args.fullscreen, "Display index": str(config["screen"]),
                     "Cue audio output": outputs}
            dialog = gui.DlgFromDict(setup, title="AIMLAB - new session", sortKeys=False)
            if not dialog.OK:
                return
            args.participant = setup["Participant ID"].strip()
            args.seed = int(setup["Seed (fixation only)"])
            args.fullscreen = setup["Fullscreen"]
            args.screen = int(setup["Display index"])
            args.audio = setup["Cue audio output"]
        config = {**config, "fullscreen": args.fullscreen or config["fullscreen"],
                  "screen": config["screen"] if args.screen is None else args.screen,
                  "audio_device": args.audio or config.get("audio_device")}
        trials = sequence(args.seed, config["blocks"], config["row_repetitions"],
                          config["fixation_min_s"], config["fixation_max_s"])
        session = Session.create(ROOT / "data", args.participant, config, trials, args.seed)
    if args.port:
        config = {**config, "preferred_port": args.port}
    if args.audio:
        config = {**config, "audio_device": args.audio}
    app = ExperimentApp(ROOT, config, session)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
