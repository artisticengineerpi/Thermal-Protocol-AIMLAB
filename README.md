# AIMLAB · single-Uno PsychoPy experiment

Double-click **Launch PsychoPy.bat**. Enter a participant ID, calibrate motor intensity and Peltier lead, save, then choose **Lock calibration & start**. The participant display and calibration controls run natively in PsychoPy; no web server is needed. Close/disconnect the previous browser serial connection or Arduino Serial Monitor first so PsychoPy can own the Uno's COM port.

Installed runtime: `C:\Program Files\PsychoPy\python.exe` (PsychoPy 2026.2.4). The launcher uses this runtime, not the unrelated system Python.

Select the cue audio output in the setup dialog. **Speakers (Realtek(R) Audio)** is the default on this laptop; PsychoPy's automatic default was the Oculus virtual headphones. Use **Test cues** on the calibration screen to check audibility before starting. This button plays sound only and also works before the Uno connects. `--audio "exact device name"` overrides the audio device when launching or resuming from a terminal.

```powershell
cd 'C:\Users\other\Desktop\Thermal-Protocol-AIMLAB'
& '.\Launch PsychoPy.bat'
# Optional explicit participant / display / port:
& '.\Launch PsychoPy.bat' --participant P07 --seed 7 --fullscreen --screen 0 --port COM5
```

All PsychoPy screens use a pure black background, white text and a white fixation cross. A small green/red dot at the top right shows connection health. Green means fresh Uno replies; red means disconnected, syncing or stale. There is no status text or visible stop/quit button.

Press **Esc** to stop all outputs, abort the current attempt and pause. Press **Q** from that pause to quit. Space deliberately repeats the aborted trial once the Uno is ready; nothing automatically restarts. These shortcuts are not printed on the experiment screen.

## Fixed study settings and calibration

- HOT drive: **183 PWM**, polarity `H` (six-participant mean 183.33, rounded). This is a drive level, not a temperature in degrees. The sleeve has no temperature sensor feedback.
- Motor motion: **4,000 ms**, M1 → M2 → M3 → M4.
- Participant calibration: common motor PWM **0–255**, step 1; Peltier lead **0–2,000 ms**, step 10 ms.
- All four motors use the same calibrated intensity. The four individual test buttons verify each channel; the four condition buttons run A/B/C/D with the selected calibration.
- Changes take effect on the next test; sliders are locked during stimulation. Calibration is frozen for the whole experimental session when Start is pressed.
- Saved calibrations are in `calibration/presets.json`; each session also stores its exact settings independently. Loading a Stern seed preset imports **motor intensity and lead only**, never its historical thermal PWM or polarity. Study HOT 183 / 4 s stay fixed for new sessions. Resumed sessions retain their saved values.
- Starting motor PWM **189** is the rounded six-participant mean (188.67). Lead still starts at **980 ms** and remains adjustable. Means are starting points, not validated optima. No gender-based automatic setting is applied. Exact inputs are recorded in `calibration/defaults-source.json`; the additional participant's approximate report is excluded from this six-person calculation.
- Support the arm/hand on an insulating armrest. Direct contact with a cold tabletop can change the sensation. The extra female participant's report of comfort around 180 PWM is recorded in `reference/pilot-observations.txt`; it is not a temperature measurement or evidence of a universal threshold.

## Exact protocol

| Letter | Delivered condition | Response label is collected independently |
|---|---|---|
| A | No stimulation | Participant chooses 1–5 |
| B | Thermal only | Participant chooses 1–5 |
| C | Moving vibration | Participant chooses 1–5 |
| D | Combined thermal + moving vibration | Participant chooses 1–5 |

Latin rows: **ABDC / BCAD / CDBA / DACB**. Concatenate the four rows, repeat twice per block: 32 trials. Repeat for 5 blocks: **160 trials, 40 of each condition**. This preserves the old repository's fixed order; the seed only changes fixation durations. It does not randomize the Latin rows.

Each trial: 500 Hz cue and fixation cross for 3–4.5 s → blank display and 1000 Hz cue with a queued Uno RUN → acknowledged hardware stimulation → hardware DONE plus confirmed all-OFF telemetry → 500 Hz cue and question → 1 s delay → response choices. Choices are 1 no sensation, 2 static thermal, 3 moving vibration, 4 moving thermal, 5 not sure. Regular number keys and numeric keypad are accepted. Reaction time begins at the flip displaying the choices; buffered keys are cleared at that flip. No response deadline. After each of the first four blocks, a 60 s break is followed by Space to continue.

The 1000 Hz cue marks the start of the stimulation command, including preheat for D. USB/OS/audio latency is not assumed to be zero: command-send, ACK, completion and display-flip host timestamps are logged separately. This implementation does **not** claim EEG-grade measured physical onset alignment. EEG triggers are not enabled.

### Timing inherited from the installed v7 firmware

| Condition | Duration |
|---|---|
| A, no stimulation | 5.0 s |
| B, thermal only | 5.0 s; enable follows 50 ms electrical settling |
| C, motors | 4.0 s |
| D, combined | calibrated lead + 4.0 s; Peltier stays on until motor motion ends |
| Individual motor E/F/G/H | 5.0 s |

This intentionally retains v7's existing A/B duration, rather than silently changing the Arduino protocol. Total exposure lengths therefore differ between conditions. Fixed **motor motion** means C/D are always 4 s; it does not mean that every condition or Peltier exposure has equal duration.

Motor SOA is **800 ms**. Each motor envelope is **1,600 ms**: 400 ms ramp up, 800 ms plateau, 400 ms ramp down. Motor onset positions are 0, 800, 1,600 and 2,400 ms relative to motion start. Combined adds the chosen lead to every motor onset; Peltier power begins after the firmware's 50 ms settling period. Thus the physical command lead is approximately selected lead minus 50 ms, and PWM ramps are updated at 20 ms intervals. PWM envelopes are not measured vibration or temperature curves.

## Connection and recovery

The small connection dot stays visible on every screen: green for fresh Uno replies, red otherwise. It does not disclose the trial condition or prove physical heating/vibration. Live channel PWM remains on the calibration screen.

The actual Uno on **COM3** was identified as v7 and confirmed all-OFF on 2026-09-30. No stimulation was sent during this check. `Check Connection.bat` repeats this no-stimulation test; close other serial owners first. The checker releases the COM port when finished.

One serial worker exclusively owns the port at 115200 baud. It identifies **AIMLAB_COMBINED_V7**, issues STOP, verifies PONG and zero-output IDLE telemetry, and only then enables testing. PING runs every 200 ms, STATUS every 100 ms. Missing PONG or STATUS for 650 ms faults the connection. The existing Uno independently switches off a protocol RUN after 750 ms without PING.

The connector automatically retries eligible Arduino/USB-serial ports. After the first successful identification it binds to USB VID/PID/serial number; if the adapter has no serial number, it binds to that COM port. This avoids silently switching to a different sleeve. An explicitly chosen `--port` supports other adapters but still requires the correct firmware identity. A changed COM port on an adapter without a unique serial number requires relaunch with the new port.

On a dropped connection or MCU reset, the active attempt is saved as **aborted**, pending RUN commands are discarded, and the worker reconnects and resynchronizes to **outputs OFF**. There is no automatic stimulus replay or mid-trial continuation. The experiment stays paused; Space repeats the same uncounted trial from fixation after the connector is READY. This preserves 160 completed trials, while logging all extra aborted exposures.

The worker requires a live display-loop pulse. If the display stalls for more than 500 ms, it stops and closes the connection; it does not continue heartbeats indefinitely behind a frozen GUI. **Esc** stops outputs and pauses a trial. **Q** saves/closes from calibration, pause or completion. The UI's live values are Uno-reported PWM register settings; they cannot detect a loose motor wire, failed driver, detached heatsink or actual skin temperature.

## Data and resuming

Every session gets a unique `data/PARTICIPANT_timestamp_id/` folder:

- `session.json`: study configuration, full 160-trial sequence, locked calibration and progress.
- `attempts.jsonl`: append-only, flushed/fsynced attempt records, including aborted attempts.
- `trials.csv`: convenient export of those attempts, responses, RT, settings, connection generation and host timing.
- `events.jsonl`: display phases, serial commands, connection events, calibration and telemetry. High-frequency telemetry/serial records are flushed but not individually fsynced; completed attempts and session snapshots are durable.

Double-click **Resume Session.bat** to select an unfinished session. Recovery rebuilds progress and CSV from committed attempt records, logs an interrupted active attempt as aborted, reconnects with outputs off, and waits for Space. A crash during an inter-block break conservatively repeats the full break. A partial final journal record is preserved separately before recovery. A resumed session retains its original configuration and calibration even if study.json has since changed.

## Files and previous work

- `aimlab/`: connector, protocol, storage, PsychoPy display.
- `study.json`: fixed study configuration; change deliberately before creating a new session.
- `firmware/Peltier_V3/Peltier_V3.ino`: byte-identical copy of your current v7 sketch. The original Arduino sketch was not edited or uploaded.
- `old protocol/2026-09-30-before-psychopy/`: all previous repository files (including its archive and utilities), with SHA-256 manifest. Git history remains at the project root.
- `old protocol/web-console-v7/`: copy of the working browser console and firmware backups.
- `reference/participant-analysis/`: original exported presets and corrected six-participant analyses.
- `reference/circuit/`: previous circuit artwork. Firmware pin mapping is authoritative: M1 D5, M2 D6, M3 D3, M4 D11; Peltier ENA D9, IN1 D8, IN2 D7; OUT1/OUT2.

## Validation

For a concise diagram, open **PROTOCOL-MAP.txt**. For wiring and step-by-step launch instructions, open **QUICK-PROTOCOL.txt**.

```powershell
& 'C:\Program Files\PsychoPy\python.exe' run_experiment.py --check
& 'C:\Program Files\PsychoPy\python.exe' -m unittest discover -s tests -v
& 'C:\Program Files\PsychoPy\python.exe' run_experiment.py --smoke-test
```

Tests use a serial emulator and temporary session directories, never real stimulation. `--smoke-test` renders the actual PsychoPy calibration and response screens to `validation/` without opening a COM port. There is no simulated-hardware mode in the participant experiment. Software tests cannot establish physical temperature, motor operation or USB reliability of this particular sleeve; a hardware check remains to be performed with this PsychoPy application.
