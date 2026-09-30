# Project checkpoint — 2026-09-25

## Current working project
- Web console: outputs/experiment; launch START.bat; http://127.0.0.1:8770/.
- Arduino sketch: C:\Users\other\Documents\Arduino\Peltier_V3\Peltier_V3.ino.
- Matching distributable sketch: outputs/experiment/Peltier_V3/Peltier_V3.ino.
- Firmware identity AIMLAB_COMBINED_V4; console requires v4.0.

## Saved configuration
- Hardware only, no EEG. HOT polarity; Peltier PWM 164.
- Motors M1–M4 PWM 83; master slider 83. All five individually adjustable live.
- M1 D5, M2 D6, M3 D3, M4 D11.
- Peltier ENA D9, IN1 D8, IN2 D7; OUT1/OUT2. Flipped mapping: HOT IN1 HIGH / IN2 LOW.
- Compact single-screen console: linear M1–M2–Peltier–M3–M4; commanded PWM telemetry, progress, individual motor tests, four condition tests, cues, participant preview, exports, STOP.
- Background protocol/log dialog retains explanatory details.

## Protocol
- A none; B thermal only; C vibration only; D combined.
- Latin square rows: ABDC, BCAD, CDBA, DACB.
- Rows repeated twice per block; 32 trials/block, 5 blocks, 160 trials.
- Fixation 3–4.5 s; stimulation 5 s; delayed response choices; 60 s block breaks plus continue.
- v4 C/D motion: M1 0–2 s, M2 1–3 s, M3 2–4 s, M4 3–5 s.
- SOA 1000 ms; each envelope 500 ms rise, 1000 ms peak, 500 ms fall. Equal commanded duration and PWM integral for equal peaks. Perceived funneling and actual motor spin time still require hardware validation.
- B has no motor output. Individual motor tests remain 5 s. Original serial shortcuts retain their existing behavior, including mode 9 repeating sweep until 5.
- Session metadata stores the new timing and protocol version.

## Validation / next action
- Host C++ tests passed: equal motor exposure and peak dwell at PWM 83, A/B/C/D output timing, thermal polarity, stop, heartbeat timeout, argument validation.
- Serial adapter tests passed; JavaScript syntax checked.
- v4 firmware saved to Arduino folder; previous version backed up there and in project backups.
- v4 has NOT been uploaded or tested on physical hardware by the assistant. Upload sketch, refresh console, reconnect Uno, test C then D.
- No temperature feedback. GUI colours represent commanded drive, not measured temperature.

## State preservation
- This checkpoint records agreed settings and implementation state, not a resumable live hardware session.
- Browser session events are saved by the app in localStorage (aimlab-last-session-v2); export JSON before starting another session. Browser-local data is not included in this filesystem archive.
- No Git repository exists in this workspace; checkpoint saved as files and ZIP instead.
- outputs includes schematics and prior printable assets. work includes generators and test harnesses; older generators are historical and may overwrite newer settings if rerun.

## Latest update — v5.0 Peltier lead
Supersedes v4 firmware requirement above. Combined D has a 0–2000 ms lead slider, default 0, 10 ms steps. Motors retain the same five-second envelope, starting after the lead; thermal window is shifted earlier without extending thermal on-time. Total sequence = 5 s + lead. Offset locked during session, PWM still live. Cue starts preheat sequence; response follows motor completion. Session metadata and per-trial events include lead. Firmware identity AIMLAB_COMBINED_V5. Host timing/serial/protocol tests passed; UI slider verified. Upload and physical testing pending.

## Latest update — 2026-09-28 v6.0
Added named Quick save/Load presets for all sliders and polarity, persisted in browser localStorage. Added C/D motion duration 1–8 s, 0.1 s steps, default 5 s, proportional equal motor envelopes. Combined thermal window min(T,5 s); preheat lead unchanged. Firmware identity AIMLAB_COMBINED_V6. Host waveform sweep (71 durations), presets, serial and protocol checks passed. Arduino upload/hardware verification pending.

## Latest appearance update — 2026-09-28
White Bootstrap 5.3.8 UI, bundled locally with MIT license. Custom rig visualization and all controls retained; compact layout verified at the current narrow browser width. Teal motors, HOT red, COLD blue, primary blue and connection status badges. No firmware change required for theme. Neon HTML/CSS backed up in experiment/backups.

## Latest update — 2026-09-30 v7.0
Combined Peltier thermal cutoff changed to lead + motion duration, ending with M4; thermal-only remains 5 s. Firmware and serial handshake updated to AIMLAB_COMBINED_V7. Current example (202 motors, 171 HOT, lead 1680 ms, motion 4100 ms): thermal powered 0.05–5.78 s from RUN; M1 envelope begins 1.68 s. All host timing/serial/protocol checks pass. Source installed in Arduino folder with backup. Upload and physical validation pending. Earlier v6 curve files remain historical. Existing connected browser was not refreshed or modified during this change.
