# Thermal in Motion · AIMLAB

A PsychoPy experiment for thermal and vibrotactile motion perception using **one Arduino Uno, one Peltier and four vibration motors**.

**160 trials · 4 conditions · 5 blocks · participant calibration · automatic Uno reconnection**

![Experimental blocks, Latin square and session timing](reference/protocol-picture/experiment-blocks-eeg-timing.png)

[Protocol checklist](PROTOCOL-MAP.txt) · [Wiring and start guide](QUICK-PROTOCOL.txt) · [Download diagram](reference/protocol-picture/experiment-blocks-eeg-timing.svg)

## Start

Tested with **PsychoPy 2026.2.4**, **pyserial 3.5**, Windows and the included **v7 Uno firmware**. The Windows launchers expect PsychoPy at `C:\Program Files\PsychoPy\python.exe`; update the launchers if it is installed elsewhere.

1. Connect the sleeve's tested external power supply and the Uno USB cable.
2. Disconnect the previous browser serial connection and close Arduino Serial Monitor. Only one application can own the port.
3. Double-click **[Launch PsychoPy.bat](Launch%20PsychoPy.bat)**.
4. Enter a participant ID and select the display and cue audio output.
5. Wait for the **green dot**. Use **Test cues**, then test M1–M4, Thermal and Combined.
6. Adjust motor intensity and Peltier lead. Select **Save calibration**, then **Lock calibration & start**.
7. Press **Space** to begin.

From PowerShell in this repository:

```powershell
& '.\Launch PsychoPy.bat'

# Optional explicit participant, display and port:
& '.\Launch PsychoPy.bat' --participant P07 --seed 7 --fullscreen --screen 0 --port COM3
```

The app opens native PsychoPy windows; no web server is needed. Choose the actual speakers/headphones in setup. The current machine's configured default is Realtek speakers. `--audio "exact device name"` can override the audio output when launching or resuming.

## Display and controls

Black background, white text and a large centered white fixation cross—three times the original size. A small dot at the top right is the only connection indicator:

- **Green:** fresh replies from the expected Uno firmware.
- **Red:** disconnected, synchronizing or stale replies; the connector retries automatically.

The dot reports communication health, not physical heating or vibration. The calibration screen also shows Uno-reported PWM values.

| Key | Action |
|---|---|
| **Esc** | Stop all outputs and cue audio; abort the current attempt and pause |
| **Q** | Quit from calibration, pause or completion; during a trial, press **Esc → Q** |
| **Space** | Begin, continue after a break, or deliberately repeat an aborted trial when connected |
| **1–5** | Answer the participant question; numeric keypad also supported |

There are **no visible stop/quit buttons**. A stopped or interrupted stimulus never restarts automatically.

## Settings and calibration

| Setting | New-session default | Participant adjustment |
|---|---:|---|
| Motor PWM, same for M1–M4 | **189** | 0–255, step 1 |
| Peltier PWM | **183, HOT** | Fixed during the study |
| Peltier lead, combined condition only | **980 ms** | 0–2000 ms, step 10 ms |
| M1 → M4 motion duration | **4.0 s** | Fixed during the study |

PWM defaults are rounded arithmetic means of the six plotted pilot participants: **188.67 motor** and **183.33 Peltier**. Inputs are recorded in [defaults-source.json](calibration/defaults-source.json). These are starting settings, not validated optima. **PWM is not measured temperature**; the firmware has no temperature feedback.

Sliders are locked during stimulation, and calibration locks for the experiment when Start is selected. Presets are saved to [calibration/presets.json](calibration/presets.json). Loading a historical pilot preset imports only motor intensity and lead; new-session thermal PWM and motion duration stay fixed. Resumed sessions retain their original saved settings.

Support the hand and arm on an insulating armrest to avoid direct contact with a cold tabletop.

## Experiment design

| Condition | Stimulus | Duration |
|---|---|---:|
| **A** | No stimulation | 5.0 s |
| **B** | Thermal only | 5.0 s |
| **C** | Moving vibration | 4.0 s |
| **D** | Thermal + moving vibration | Lead + 4.0 s; **4.98 s** by default |

The fixed Latin-square order is:

```text
A B D C
B C A D
C D B A
D A C B
```

Read each row left to right, then move down. Run all four rows **twice total per block**: 32 trials. Repeat for **five blocks**: 160 completed trials, **40 per condition**. After each of the first four blocks, take a **60-second break**, then press Space.

The seed changes randomized fixation times only. It does not shuffle the Latin rows. Five blocks preserve the existing study design; five is not a requirement of a Latin square.

### One trial

```text
500 Hz cue + fixation cross (random 3–4.5 s)
    → 1000 Hz cue + condition A/B/C/D
    → Uno completion + confirmed outputs OFF
    → 500 Hz cue + question; wait 1 s
    → show choices; receive response; save
    → next trial
```

During stimulation, the screen is black apart from the connection dot. Response choices are **1 No sensation**, **2 Static thermal**, **3 Moving vibration**, **4 Moving thermal**, **5 Not sure**. There is no response deadline. Reaction time starts at the screen flip that displays the choices; earlier buffered keys are cleared. Responses are recorded independently of the delivered condition.

### Motion and Peltier timing

Motor starts are **0, 0.8, 1.6 and 2.4 s** relative to motion onset. The start-to-start gap (**SOA**) is 800 ms. Every motor has the same 1.6-second envelope: **0.4 s rise → 0.8 s steady → 0.4 s fall**. Adjacent envelopes overlap; M4 ends at 4 s.

For combined stimulation, all motor onsets shift by the calibrated lead. The Peltier enables after **50 ms electrical settling** and stays on until the complete motor stroke ends. Firmware updates motor PWM at 20 ms intervals. Thermal-only and no-stimulation trials retain the v7 firmware's 5-second duration; individual motor tests also last 5 seconds.

### Session duration and EEG

| Part | Estimated time |
|---|---:|
| EEG gel preparation | **15 min** |
| Experiment, including scheduled breaks | **32–37 min** |
| Gel preparation + experiment | **47–52 min** |

Experiment timing assumes the 980 ms lead and average responses of 1–3 seconds. Calibration, extra setup, longer pauses and repeated trials add time.

**EEG preparation is included in scheduling; EEG trigger output is not implemented in this PsychoPy version.** The 1000 Hz cue marks the stimulation command, including preheat in D. Host send/ACK/completion and display-flip timestamps are logged, but physical onset synchronization has not been measured.

## Uno wiring and firmware

| Function | Uno pin / connection |
|---|---|
| Motor 1 | **D5**, through its motor driver |
| Motor 2 | **D6**, through its motor driver |
| Motor 3 | **D3**, through its motor driver |
| Motor 4 | **D11**, through its motor driver |
| Peltier ENA | **D9**; remove the L298N ENA jumper |
| Peltier IN1 / IN2 | **D8 / D7** |
| Peltier leads | L298N **OUT1 / OUT2**, retaining the tested orientation |
| Ground | Uno, drivers and external supply share ground |

Use the sleeve's tested external supply, driver logic-power arrangement, heatsink and fan. Do not power the Peltier or motors directly from Uno pins. The **ENA** jumper and module **5V regulator** jumper are different; see the [wiring guide](QUICK-PROTOCOL.txt) before changing connections.

The required sketch is [firmware/Peltier_V3/Peltier_V3.ino](firmware/Peltier_V3/Peltier_V3.ino), identity **`AIMLAB_COMBINED_V7`**, at **115200 baud**. If needed, upload it using Arduino IDE with board **Arduino Uno** and the board's current COM port, then close Serial Monitor. The app verifies firmware identity before enabling stimulation.

## Connection monitoring and recovery

The serial worker identifies the Uno, sends STOP and confirms PONG plus zero-output IDLE status before enabling tests. It sends **PING every 200 ms** and requests **STATUS every 100 ms**. Missing either reply for 650 ms faults the connection; the Uno independently stops a protocol run after 750 ms without PING. A display-loop stall longer than 500 ms also requests stop and closes the connection.

```text
Link lost → abort and log attempt → discard pending RUN commands
    → reconnect → confirm outputs OFF → pause
    → Space repeats the same uncounted trial from fixation
```

After identification, reconnection binds to the USB device's VID/PID/serial number, or its COM port if no unique serial number exists. A port change on an adapter without a serial number requires relaunching with the new `--port`.

**[Check Connection.bat](Check%20Connection.bat)** performs an identification/all-OFF check without stimulation and releases the port afterward. Close other serial applications first. On **2026-09-30**, the local Uno on **COM3** passed this check with v7 and all five reported outputs at zero. Port numbers may change.

## Saved data and resume

Each session creates `data/PARTICIPANT_timestamp_id/`:

| File | Contents |
|---|---|
| `session.json` | Configuration, full sequence, calibration and progress |
| `attempts.jsonl` | Completed and aborted attempts; durable append-only journal |
| `trials.csv` | Attempt status, responses, RT, settings and timing export |
| `events.jsonl` | Display phases, serial commands, connection events and PWM reports |

Double-click **[Resume Session.bat](Resume%20Session.bat)** to select an unfinished session. Recovery rebuilds progress from committed attempts, preserves interrupted attempts as aborted, confirms outputs OFF and waits for deliberate continuation. If recovery occurs at a block boundary, the full break is repeated. Saved session settings take precedence over later changes to `study.json`.

## Project files

| Path | Purpose |
|---|---|
| [aimlab/](aimlab/) | PsychoPy UI, protocol, serial connector and data storage |
| [study.json](study.json) | New-session defaults and study configuration |
| [calibration/](calibration/) | Saved calibration presets and default provenance |
| [firmware/](firmware/) | Single-Uno v7 sketch |
| [reference/](reference/) | Protocol diagrams, pilot analysis and historical circuit artwork |
| [tests/](tests/) | Protocol, recovery, storage and connection tests |
| [old protocol/](old%20protocol/) | Previous two-controller protocol and archived web console |

## Validation

Run from the repository directory:

```powershell
& 'C:\Program Files\PsychoPy\python.exe' run_experiment.py --check
& 'C:\Program Files\PsychoPy\python.exe' -m unittest discover -s tests -v
& 'C:\Program Files\PsychoPy\python.exe' run_experiment.py --smoke-test
```

Automated tests exercise the full 160-trial flow, breaks, recovery, defaults and connection failures using a serial emulator. The display check renders native PsychoPy screenshots without opening a COM port. The participant app itself requires real hardware.

The real Uno identification/all-OFF check passed. Physical sleeve actuation, unplug/reconnect behaviour on this board, cue audibility and physical stimulus timing still need validation in the new app. Uno telemetry cannot detect actual skin temperature, disconnected actuator wires or physical vibration.
