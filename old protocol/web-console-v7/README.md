# AIMLAB combined-Uno experiment — no EEG

## Start

1. Upload `C:\Users\other\Documents\Arduino\Peltier_V3\Peltier_V3.ino` in Arduino IDE, selecting Uno and its COM port. Close Serial Monitor afterward so the GUI can open the port.
2. Double-click `START.bat` in this directory. Open **http://127.0.0.1:8770** in **Chrome or Edge**. Keep the launcher window open. Node.js is the only server dependency; there is no npm install step.
3. The GUI is hardware-only. Peltier defaults to **HOT at PWM 164**. Four separate motor sliders default to **83 each**. Click **Test cues** to check speaker output.
4. Click **Connect Uno** and select its USB port. The GUI verifies firmware identity, confirms outputs are stopped, and tests PING/PONG before displaying CONNECTED. **Test connection** repeats PING/PONG without activating outputs and reports latency. Idle connections are checked every 2 seconds. Timeout/unplugging shows DISCONNECTED and disables test starts. Tests are enabled once the Uno connection is verified.
5. Open the participant display, move it to the participant monitor, and use the browser's F11 fullscreen command if desired. The console preview is also functional if a second window is not needed. Closing a participant window during a run stops that session.
6. Click **Start full experiment**, then Continue/Space. Respond using buttons or keys 1–5. Esc or STOP ALL stops the session. After each 60-second block break, Continue/Space starts the next block.
7. Download JSON and CSV before starting another session. **Export last saved session** retrieves the latest locally saved session after reload; this is data recovery, not mid-session resumption. The next session replaces this last-session cache. Browser private mode or clearing site data can remove it.

The saved working bench sketch is:
`C:\Users\other\Documents\Arduino\Peltier_V3\backups\Peltier_V3-working-v1.6-20260925-044302.ino.bak`
It is outside the sketch source root and has a `.bak` extension so Arduino will not compile it along with the active sketch. To restore, copy its contents over the active `.ino` and upload.

## Four conditions and Latin square

| Code | Condition | Peltier | Motors |
|---|---|---|---|
| A | No stimulation | Off | Off |
| B | Thermal only | Selected polarity, default PWM 164 | Off |
| C | Vibrotactile only | Off | Hold motor 1 for 2 s, then move 1 → 4 over 3 s |
| D | Combined thermal motion | Same as B | Same as C |

| Row | Position 1 | Position 2 | Position 3 | Position 4 |
|---|---|---|---|---|
| 1 | A | B | D | C |
| 2 | B | C | A | D |
| 3 | C | D | B | A |
| 4 | D | A | C | B |

The existing repository executes all four rows in this fixed order, twice per block, for five blocks:

`ABDC BCAD CDBA DACB ABDC BCAD CDBA DACB`

That is **32 trials per block, 160 total, 8 occurrences of each condition per block and 40 overall**. The GUI preserves this design. These four rows balance positions and all 12 directed transitions *within rows*. Concatenating rows adds boundary transitions, so the entire continuous sequence is not perfectly first-order carryover balanced. This is not a participant-specific single-row assignment; change the design explicitly if that is required for your study.

## Each complete trial

1. 500 Hz tone (150 ms) and fixation cross for a seeded random 3.0–4.5 seconds.
2. Blank participant screen, 1000 Hz tone (150 ms), and a request for the assigned condition.
3. Uno performs a 5-second trial autonomously. Thermal conditions have a 50 ms disabled settling interval included in the 5 seconds. Motor conditions hold motor 1 from 0–2 s, then perform one forward stroke from 2–5 s.
4. Uno turns all outputs off and acknowledges completion. GUI plays a 500 Hz tone and displays “What did you feel?”
5. After 1 second, response options unlock: 1 none, 2 thermal, 3 vibration, 4 thermal motion, 5 unsure. Early/held keys are ignored. Response time is measured from options becoming available.
6. Next trial follows the response. A 60-second break follows each block except the last; operator/participant Continue is required afterward.

No EEG device is opened and no EEG markers are emitted. Audio and screen events are software timestamps, not measured physical stimulus onset; JSON includes serial acknowledgement latency. Original WAV lengths were not established; this version explicitly synthesizes 150 ms tones with short fades instead of depending on files in Downloads.

## Debug

The four A/B/C/D buttons run one 5-second condition with no cues or response question by default. Check **Include trial cues** to run one complete cued trial. Session identity/sequence controls are disabled during a session. The five PWM sliders and polarity selector remain editable at any time. Live edits are recorded as settings_requested and settings_applied events in JSON. Per-trial stimulus_requested records the settings at trial start. Edits during a trial make stimulus intensity variable; use JSON, not response-only CSV, to audit them. A polarity change disables thermal power for 50 ms without extending the trial deadline. Changing settings while idle only prepares the next test; it does not energize anything. STOP is always available.

The prior Serial Monitor shortcuts remain: 1–4 individual motors at 255 for 1 s, 5 stop, 6 hot, 7 cold, 8 hot/pause/cold, 9 repeat the back-and-forth sweep until stopped. The experiment stroke is distinct from shortcut 9.

## Confirmed wiring and protocol changes

Motors 1–4 = **D5, D6, D3, D11**. Peltier ENA D9, IN1 D8, IN2 D7. The user-flipped polarity is retained: HOT sets IN1 HIGH/IN2 LOW; COLD sets IN1 LOW/IN2 HIGH.

Source protocol: `C:\Users\other\Desktop\Thermal-Protocol-AIMLAB\thermal_motion_cli_v2.py`, with the interpolation from `Thermal-in-Motion-AIMLAB\motor_controller\motor_controller.ino`.

The original protocol's overlap factor 1 is retained for experiment strokes. Five live sliders control Peltier PWM (default 164) and each motor peak (default 83). The default polarity is HOT with the flipped mapping. Individual motors E/F/G/H can be tested from their own buttons for 5 seconds. Serial shortcuts 1–9 keep their existing behavior, including their previous bench-test PWM defaults.

## Shutdown and limitations

- RUN is a bounded 5-second operation on the Uno, not a stream of host-timed actuator writes.
- GUI sends PING every 200 ms during RUN. Firmware shuts off on 750 ms without a heartbeat. Link loss, malformed commands, busy RUN requests and explicit stop disable outputs.
- A frozen firmware/failed driver is not covered by a software timer. Temperature sensing and independent thermal protection have not been implemented. This software is ready for supervised bench verification; it is not evidence that repeated skin-contact trials are safe.
- Keep both browser windows visible and the computer awake. Browser timer throttling can cause a protective heartbeat stop. It aborts the trial rather than silently continuing. GUI timing is not EEG-grade synchronization.
- Physical heatsink/fan, ratings and power cutoff still need hardware verification.
- No participant session is uploaded anywhere. Local server binds to 127.0.0.1. Avoid names or other identifying information in session codes.

## Serial API

`IDENTIFY` → `AIMLAB_COMBINED_V3`

`RUN <A..H> <H|C> <thermalPWM> <motor1PWM> <motor2PWM> <motor3PWM> <motor4PWM>` (all PWM values 0..255; E..H test motors 1..4 individually) → `ACK RUN <condition>` → `DONE RUN <condition>`

`PING` → `PONG`; `5`, `STOP`, `OFF` or immediate `!` stops. `FAULT HEARTBEAT` means communications stopped for 750 ms; `FAULT BUSY` means RUN was sent while a test was active. The GUI validates identity and waits for both start and completion acknowledgements.

Web Serial requires a browser-supported user port chooser; see [Chrome's Web Serial documentation](https://developer.chrome.com/docs/capabilities/serial).

## Validation

`node test-protocol.mjs` checks 160-trial composition, condition counts, Latin balance, cue order, break count, response timing, all four debug conditions and abort handling with a simulated clock.

Host C++ tests execute the actual sketch against mock Arduino I/O to check A/B/C/D output patterns, five-second completion, heartbeat timeout, busy/malformed rejection, polarity, stops, plus regression coverage for the existing serial shortcuts and infinite sweep. These do not substitute for an AVR build or physical timing/temperature measurements.

The earlier GUI was exercised in simulation for a combined debug run, a complete cued trial with response, and stopping a full session. The current GUI removes simulation; automated tests still use mocks without touching hardware. Serial adapter tests cover ACK/DONE matching, faults, cancellation and timeout. Windows returned “Access is denied” when launching the installed Arduino CLI, so an AVR build and upload were not performed here. Compile/upload from Arduino IDE before connecting hardware.

Live command: `SET H|C thermalPWM motor1PWM motor2PWM motor3PWM motor4PWM` → `ACK SET`. Firmware v3 is required; upload the new sketch before reconnecting. The v2 sketch is backed up as `Peltier_V3/backups/Peltier_V3-before-live-sliders-v2.ino.bak`.

Live rig: motor 1 — motor 2 — Peltier — motor 3 — motor 4. PWM bars and Peltier colour use Uno STATUS reports every 200 ms during tests. Grey is off, red HOT, blue COLD; this is drive status, not measured temperature. Stale/disconnected values show dashes. The overall 5-second progress bar uses host time from the RUN acknowledgement. Master motor PWM sets all four motor sliders together; individual edits show Mixed. No firmware update beyond v3 is needed for this view.


## Motion revision v4.0
Upload v4.0 before using the updated console (the firmware handshake requires it). This supersedes the original M1 hold/stroke timing above. C and D use equal 2000 ms envelopes, 1000 ms SOA, 500 ms rise, 1000 ms peak, 500 ms fall. Windows: M1 0–2 s, M2 1–3 s, M3 2–4 s, M4 3–5 s. A/B and individual tests are unchanged. Equal commanded envelopes do not guarantee equal perceived intensity or motor spin time. Tune on the rig; this is an overlapping apparent-motion candidate, not a validated funneling illusion. Session metadata records these timings.
## Peltier lead — v5.0
Combined mode D adds a 0–2000 ms lead slider (10 ms steps, default 0). Choose it before starting a run; it is locked during a session. PWM remains live. Firmware starts the thermal window at RUN and shifts the unchanged motor envelope later by the lead. Thermal cutoff remains 5000 ms after RUN (including the existing 50 ms settling interval); completion is 5000 + lead ms after RUN. Thus at 1000 ms lead, relative to motor onset, thermal is approximately -950 to 4000 ms and motors are 0 to 5000 ms. The existing settling delay is preserved at all offsets. Other conditions ignore the offset. The stimulation cue marks the beginning of the combined sequence, including preheat, and the response cue occurs after the motors finish. The selected offset is logged per trial. The live progress display includes preheat.
Upload v5.0 firmware (AIMLAB_COMBINED_V5) before reconnecting; old firmware is rejected. Host tests cover lead limits, thermal cutoff, unchanged motor envelopes, preheat stop/watchdog, and existing protocol/serial tests. Physical upload/testing remains pending.

## v6.0 — demo presets and duration
Quick save stores a named preset in browser localStorage (aimlab-presets-v1); saving the same name replaces it. Select a preset and Load to restore all PWM sliders, master value, HOT/COLD, lead and motion duration. Loading never starts outputs and is locked during sessions. Records survive refresh in the same browser/origin; they are not included in project ZIPs.
Motion duration is 1.0–8.0 seconds in 0.1-second steps, default 5.0. It applies to C/D only. SOA=T/5, envelope=2T/5, rise/fall=T/10, peak=T/5. Other conditions and individual motor tests remain 5 s. Combined thermal cutoff=min(T,5 s) after RUN, including the existing 50 ms settling; motor sequence starts after the configured lead and completes at lead+T. Long motor trials do not extend heating beyond 5 s. Timing is fixed during sessions; PWM remains live. Per-trial duration is logged.
Requires firmware AIMLAB_COMBINED_V6. Host waveform checks passed for all 71 durations and 0/1000/2000 ms leads; preset validation/roundtrip and existing serial/protocol checks passed. Upload and physical verification remain pending.

## Light UI — 2026-09-28
Bootstrap 5.3.8 CSS is bundled locally under vendor/ (MIT license included; official SHA-384 verified), using Bootstrap buttons, forms, ranges, badges, and tables. No CDN connection or build step is required at runtime. Custom motor/Peltier telemetry components use teal motors, red HOT, blue COLD and grey OFF. Console and participant view now use light backgrounds. Firmware and experiment timing remain v6.0. Previous neon HTML/CSS retained in backups. Library source: https://getbootstrap.com/docs/5.3/getting-started/download/

## Simplified demo interface — 2026-09-28
Main screen prioritizes intensity, timing, presets and four large sensation buttons. Connect and STOP stay in the header. Setup contains session fields, connection diagnostics, cue check, full experiment start, protocol/logs and exports. Continue/progress and participant view remain on main screen. Larger hit targets and slider thumbs; small windows scroll instead of compressing controls. All existing element IDs retained exactly once; setup access verified in browser. Firmware unchanged.

## Tactile light styling
Added subtle bevels and highlights, raised buttons with pressed states, recessed slider tracks and fields, tinted motor tiles, a silver-grey inactive Peltier tile, and red/blue thermal states. Increased component edge contrast while preserving large click targets. No hardware or protocol changes.

## v7.0 — combined Peltier ends with M4 (2026-09-30)
Supersedes earlier combined thermal cutoffs. D starts thermal drive after the existing 50 ms settling delay and keeps it enabled through preheat and the full motor sequence. All outputs stop at lead + motion duration. Thermal-only B remains 5 s; motor waveforms, live PWM/polarity changes, STOP and heartbeat shutdown are unchanged. With 1680 ms lead and 4100 ms motion, thermal drive is 50–5780 ms after RUN (5730 ms powered), or -1.63 to 4.10 s relative to the M1 envelope. At maximum sliders, combined sequence is 10 s (9950 ms powered absent changes). Live zero PWM, polarity reversal, STOP and faults can interrupt drive as before.
Upload firmware AIMLAB_COMBINED_V7, then refresh console and reconnect. UI requires v7 so previous cutoff firmware cannot be mistaken for the new behavior. Host tests cover all 71 durations with four leads, the screenshot settings, unchanged thermal-only HOT/COLD, motor envelopes, STOP/watchdog, and existing serial/protocol tests. Arduino upload and physical verification remain pending. Old plotted curves describe v6 and are historical.
