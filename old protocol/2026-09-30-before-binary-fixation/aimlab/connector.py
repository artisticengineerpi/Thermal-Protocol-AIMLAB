"""Single-owner serial worker with acknowledged runs and fail-closed recovery.

Reconnect never resumes power. Every connection must identify the firmware,
STOP, answer PING, and report zero outputs before becoming READY.
"""
from dataclasses import dataclass, field
import queue
import re
import threading
import time
import uuid

from .protocol import FIRMWARE_ID

STATUS = re.compile(r"^Mode: (.+?) \| Peltier PWM=(\d+) polarity=(HOT|COLD)"
                    r" \| Motors PWM=(\d+),(\d+),(\d+),(\d+)$")


def parse_status(line):
    match = STATUS.fullmatch(line)
    if not match:
        return None
    mode, peltier, polarity, *motors = match.groups()
    values = [int(peltier)] + list(map(int, motors))
    if any(v > 255 for v in values):
        raise ValueError("Invalid PWM telemetry")
    return {"mode": mode, "thermal": values[0], "motors": values[1:], "polarity": polarity}


def is_off(status):
    return status is not None and status["mode"] == "IDLE" and not (
        status["thermal"] or any(status["motors"]))


@dataclass
class RunTicket:
    condition: str
    settings: object
    generation: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sent: float = 0
    ack: float = 0
    done_received: float = 0
    finished: float = 0
    error: str = ""


class UnoConnector:
    def __init__(self, preferred_port=None, serial_factory=None, port_provider=None,
                 boot_wait=2.2, retry_s=1.5):
        if serial_factory is None:
            import serial
            serial_factory = serial.Serial
        if port_provider is None:
            from serial.tools.list_ports import comports
            port_provider = comports
        self.factory, self.ports = serial_factory, port_provider
        self.preferred_port = preferred_port
        self.boot_wait, self.retry_s = boot_wait, retry_s
        self.events = queue.Queue(maxsize=5000)
        self.requests = queue.Queue(maxsize=1)
        self.lock = threading.RLock()
        self.quit = threading.Event()
        self.stop_requested = threading.Event()
        self.thread = None
        self.serial = None
        self.buffer = b""
        self.pulse_time = time.monotonic()
        self.bound_identity = None
        self.active = None
        self.reserved = False
        self.last_pong = 0
        self.last_status = 0
        self.next_ping = 0
        self.next_status = 0
        self.state = {"state": "SEARCHING", "detail": "Looking for the sleeve Uno",
                      "port": None, "firmware": None, "generation": 0,
                      "fault_count": 0, "telemetry": None, "status_at": 0}

    def emit(self, kind, **values):
        try:
            self.events.put_nowait({"kind": kind, "monotonic": time.monotonic(), **values})
        except queue.Full:
            # Logging overload is visible as a fault; do not continue collecting
            # trials when the main thread cannot consume the monitoring stream.
            self.stop_requested.set()

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def pulse(self):
        # Called only from the display loop. A frozen GUI cannot keep power alive.
        self.pulse_time = time.monotonic()

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._worker, name="sleeve-serial", daemon=True)
            self.thread.start()

    def run(self, condition, settings):
        settings.command(condition)  # validate before reserving the connection
        with self.lock:
            if self.state["state"] != "READY" or self.reserved:
                raise RuntimeError("Uno is not ready and idle")
            if time.monotonic() - self.state["status_at"] > .6:
                raise RuntimeError("Uno telemetry is stale")
            ticket = RunTicket(condition, settings, self.state["generation"])
            self.reserved = True
            self.requests.put_nowait(ticket)
        return ticket

    def stop(self):
        self.stop_requested.set()

    def close(self):
        self.quit.set()
        self.stop_requested.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _write(self, text):
        payload = (text + "\n").encode("ascii")
        if self.serial.write(payload) != len(payload):
            raise IOError("Incomplete serial write")
        self.emit("serial_tx", line=text)

    def _lines(self):
        waiting = self.serial.in_waiting
        if waiting:
            self.buffer += self.serial.read(min(waiting, 4096))
        if len(self.buffer) > 8192:
            raise IOError("Serial input overflow")
        lines = []
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            text = line.decode("ascii", errors="replace").strip()
            if text:
                lines.append(text)
        return lines

    def _exchange(self, command, accepts, timeout=1.0):
        self._write(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.quit.is_set():
                raise IOError("Closing")
            for line in self._lines():
                if accepts(line):
                    return line
            self.quit.wait(.01)
        raise IOError(f"No valid reply to {command}")

    def _candidates(self):
        ports = list(self.ports())
        if self.preferred_port:
            ports.sort(key=lambda p: p.device != self.preferred_port)
        for port in ports:
            identity = (port.vid, port.pid, port.serial_number) if port.serial_number else (port.device,)
            if self.bound_identity is not None and identity != self.bound_identity:
                continue
            # Do not probe Bluetooth, motherboard ports, or an EEG trigger box.
            if port.device != self.preferred_port and port.vid not in (0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4):
                continue
            yield port, identity

    def _connect(self, port, identity):
        self.update(state="CONNECTING", detail=f"Opening {port.device}", port=port.device,
                    telemetry=None, status_at=0)
        self.serial = self.factory(port=port.device, baudrate=115200, timeout=0,
                                   write_timeout=.2)
        self.buffer = b""
        if self.quit.wait(self.boot_wait):
            raise IOError("Closing")
        self.serial.reset_input_buffer()
        self._exchange("IDENTIFY", lambda s: s == FIRMWARE_ID)
        self.update(state="SYNCING", detail="Identified v7; confirming all outputs OFF")
        self._exchange("STOP", lambda s: s == "STOPPED: all outputs OFF")
        self._exchange("PING", lambda s: s == "PONG")
        line = self._exchange("STATUS", lambda s: is_off(parse_status(s)))
        now = time.monotonic()
        self.last_pong = self.last_status = now
        self.next_ping = self.next_status = now
        self.bound_identity = identity
        with self.lock:
            generation = self.state["generation"] + 1
            self.state.update(state="READY", detail="Connected; outputs OFF", firmware=FIRMWARE_ID,
                              generation=generation, telemetry=parse_status(line), status_at=now)
        self.emit("connected", port=port.device, identity=identity, generation=generation)

    def _cancel_pending(self, reason):
        if self.active:
            self.active.error = reason
            self.emit("run_failed", ticket=self.active.id, reason=reason)
            self.active = None
        while True:
            try:
                self.requests.get_nowait().error = reason
            except queue.Empty:
                break
        with self.lock:
            self.reserved = False

    def _drop(self, reason):
        with self.lock:
            self.state.update(state="DISCONNECTED", detail=reason, telemetry=None, status_at=0,
                              fault_count=self.state["fault_count"] + 1)
        self._cancel_pending(reason)
        if self.serial:
            try:
                self._write("!\nSTOP")
            except Exception:
                pass
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self.emit("link_fault", reason=reason)

    def _handle(self, line, now):
        if line == "PONG":
            self.last_pong = now
            return
        status = parse_status(line)
        if status:
            self.last_status = now
            self.update(telemetry=status, status_at=now)
            self.emit("telemetry", **status)
            active = self.active
            if active and active.done_received and is_off(status):
                active.finished = now
                self.emit("run_finished", ticket=active.id, condition=active.condition)
                self.active = None
                with self.lock:
                    self.reserved = False
                    self.state.update(state="READY", detail="Connected; outputs OFF")
            elif not active and not is_off(status):
                raise IOError("Unexpected active outputs while idle")
            elif active and active.ack and now - active.ack > .25 and not active.done_received:
                if status["mode"] != "PROTOCOL" and now - active.sent < active.settings.duration_s(active.condition) - .1:
                    raise IOError("Trial ended before expected duration")
                if status["thermal"] > active.settings.thermal_pwm or any(
                    m > active.settings.motor_pwm for m in status["motors"]):
                    raise IOError("Telemetry exceeds requested PWM")
                if active.condition in "ACEFGH" and status["thermal"]:
                    raise IOError("Unexpected thermal output")
                if active.condition in "AB" and any(status["motors"]):
                    raise IOError("Unexpected motor output")
                if status["thermal"] and status["polarity"] != "HOT":
                    raise IOError("Unexpected thermal polarity")
                age = now - active.sent
                duration = active.settings.duration_s(active.condition)
                # Check stable plateaus, leaving room for USB/20 ms firmware
                # sampling delay at boundaries. These remain register checks,
                # not evidence of physical temperature or motor movement.
                if .3 < age < duration - .2:
                    if active.condition in "BD" and status["thermal"] != active.settings.thermal_pwm:
                        raise IOError("Peltier PWM does not match the requested plateau")
                    if active.condition in "EFGH":
                        expected = [0,0,0,0]
                        expected[ord(active.condition)-ord("E")] = active.settings.motor_pwm
                        if status["motors"] != expected:
                            raise IOError("Individual motor PWM/channel mismatch")
                    if active.condition in "CD":
                        motion_age = age - (active.settings.lead_ms/1000 if active.condition == "D" else 0)
                        ramp = active.settings.motion_ms / 10000
                        if ramp+.2 < motion_age < active.settings.motion_ms/1000-ramp-.2:
                            if max(status["motors"]) != active.settings.motor_pwm:
                                raise IOError("Motor PWM does not match the requested plateau")
            return
        if line.startswith("ACK RUN "):
            if not self.active or line != "ACK RUN " + self.active.condition or self.active.ack:
                raise IOError("Unexpected RUN acknowledgement")
            self.active.ack = now
            self.emit("run_ack", ticket=self.active.id, condition=self.active.condition)
        elif line.startswith("DONE RUN "):
            if not self.active or not self.active.ack or line != "DONE RUN " + self.active.condition:
                raise IOError("Unexpected trial completion")
            if now - self.active.sent < self.active.settings.duration_s(self.active.condition) - .15:
                raise IOError("Early trial completion")
            self.active.done_received = now
            self._write("STATUS")
        elif line.startswith(("FAULT", "ERROR", "AIMLAB TEST", "AIMLAB_COMBINED")):
            raise IOError("Uno: " + line)

    def _tick(self):
        now = time.monotonic()
        if now - self.pulse_time > .5:
            raise IOError("Display loop stalled; output stopped")
        if self.stop_requested.is_set():
            self.stop_requested.clear()
            self.update(state="SYNCING", detail="Stopping and confirming outputs OFF")
            self._cancel_pending("Stopped by operator")
            self._write("!\nSTOP")
            # Remove old ACK/DONE replies through a STOP barrier, then query OFF.
            self._exchange("STOP", lambda s: s == "STOPPED: all outputs OFF")
            line = self._exchange("STATUS", lambda s: is_off(parse_status(s)))
            self.last_status = time.monotonic()
            self.update(state="READY", detail="Stopped; outputs OFF", telemetry=parse_status(line),
                        status_at=self.last_status)
            self.emit("operator_stop")
        for line in self._lines():
            self._handle(line, time.monotonic())
        if now >= self.next_ping:
            self._write("PING")
            self.next_ping = now + .2
        if now >= self.next_status:
            self._write("STATUS")
            self.next_status = now + .1
        if now - self.last_pong > .65 or now - self.last_status > .65:
            raise IOError("Uno heartbeat or telemetry timeout")
        if self.active:
            if not self.active.ack and now - self.active.sent > .5:
                raise IOError("RUN acknowledgement timeout")
            if now - self.active.sent > self.active.settings.duration_s(self.active.condition) + 1:
                raise IOError("Trial completion / output-OFF confirmation timeout")
        else:
            try:
                ticket = self.requests.get_nowait()
            except queue.Empty:
                ticket = None
            if ticket:
                if ticket.generation != self.state["generation"] or not is_off(self.state["telemetry"]):
                    ticket.error = "Connection changed before RUN"
                    self.reserved = False
                else:
                    self.active = ticket
                    ticket.sent = time.monotonic()
                    self._write(ticket.settings.command(ticket.condition))
                    self.update(state="RUNNING", detail="Running " + ticket.condition)
                    self.emit("run_sent", ticket=ticket.id, condition=ticket.condition,
                              settings=ticket.settings.to_dict(), generation=ticket.generation)

    def _worker(self):
        retry_at = 0
        try:
            while not self.quit.is_set():
                if self.serial:
                    try:
                        self._tick()
                    except Exception as exc:
                        self._drop(str(exc))
                        retry_at = time.monotonic() + self.retry_s
                elif time.monotonic() >= retry_at and time.monotonic() - self.pulse_time < .5:
                    try:
                        candidates = list(self._candidates())
                    except Exception as exc:
                        self.update(state="SEARCHING", detail="Port scan failed; retrying: " + str(exc))
                        self.emit("port_scan_failed", reason=str(exc))
                        retry_at = time.monotonic() + self.retry_s
                        continue
                    if not candidates:
                        self.update(state="SEARCHING", detail="Uno not found; reconnect USB (retrying)")
                    for port, identity in candidates:
                        try:
                            self._connect(port, identity)
                            break
                        except Exception as exc:
                            self._drop(f"{port.device}: {exc}. Close the web serial console if it owns this port.")
                    retry_at = time.monotonic() + self.retry_s
                self.quit.wait(.01)
        except Exception as exc:
            self._drop("Connector failure: " + str(exc))
        finally:
            self._drop("Connector closed")
