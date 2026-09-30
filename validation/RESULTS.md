# Validation · 2026-09-30

- Installed PsychoPy 2026.2.4 and pyserial 3.5 import successfully through the standalone PsychoPy Python.
- Study configuration validates: motor PWM 189 and HOT PWM 183 (rounded means of the six plotted participants); motor motion 4,000 ms; 160 trials; fixed original Latin rows.
- **23 automated tests passed**, including a full 160-response state-machine run, four inter-block breaks, reaction-key gating, serial unplug/reconnect, missing ACK, stale telemetry despite PONG, a stalled display loop, PWM mismatch detection, device identity binding, port-scan recovery, operator STOP, recovery of aborted attempts, saved calibration, crash/torn-journal recovery, mean-derived defaults and condition-neutral persistent connection status.
- Python source compiles successfully.
- Native PsychoPy calibration and response screens rendered and were visually inspected. PNGs are in this folder. No COM ports were opened for these previews.
- Both audio cue buffers initialized explicitly on `Speakers (Realtek(R) Audio)`. Sound audibility was not tested; use Test cues in the app.
- All 20 archived original files matched their SHA-256 archive manifest after relocation.
- Included Uno sketch is byte-identical to `C:\Users\other\Documents\Arduino\Peltier_V3\Peltier_V3.ino`. Firmware was not modified or uploaded.

The real Uno on COM3 passed an IDENTIFY / STOP / PING / STATUS check on 2026-09-30: AIMLAB_COMBINED_V7, IDLE, Peltier PWM 0 and all four motors PWM 0. No RUN/stimulation command was sent. The port was released after checking. Details: last-connection-check.json.

Real sleeve actuation, physical USB unplug/reconnect behaviour with this board, actual heating/vibration, cue audibility, and physical onset latency have not yet been verified in the new PsychoPy app. Reconnect fault tests use a serial emulator. The app requires the v7 firmware identity; it will refuse to stimulate an unsupported device.

PsychoPy reported the absence of a saved monitor calibration and some long frames during preview initialization/screen capture. The study uses normalized display coordinates, logs dropped frames and host event timestamps, and does not claim calibrated visual angles or measured physical onset synchronization. Arduino firmware owns motor-envelope timing.


## 2026-09-30: protocol v2

- 28 unit/integration tests passed, including a complete simulated 160-trial session, cue order, binary fixation, hidden experiment status dot, reconnection failure and durable saved data.
- Native PsychoPy previews rendered and visually inspected: cross and filled circle have matching bounds; one response screen includes all five choices.
- Preview opened no serial port and activated no hardware. Audio/physical onset synchronization was not measured.
- Previous runtime backed up in old protocol/2026-09-30-before-binary-fixation.
