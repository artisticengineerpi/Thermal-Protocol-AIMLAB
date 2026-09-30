"""Fault injection uses a serial emulator, never a real device."""
from dataclasses import dataclass
from types import SimpleNamespace
import time
import unittest
from aimlab.connector import UnoConnector, RunTicket, parse_status
from aimlab.protocol import Settings


@dataclass(frozen=True)
class FastSettings(Settings):
    def duration_s(self, condition):
        return .25


class Board:
    def __init__(self):
        self.lines = bytearray()
        self.unplugged = False
        self.silent_status = False
        self.wrong_id = False
        self.suppress_ack = False
        self.active = None
        self.end_at = 0
        self.commands = []
        self.open_count = 0

    def factory(self, **kwargs):
        if self.unplugged:
            raise OSError("Unplugged")
        self.open_count += 1
        self.active = None
        return self

    def reply(self, text):
        self.lines.extend((text + "\n").encode())

    @property
    def in_waiting(self):
        if self.unplugged:
            raise OSError("USB cable removed")
        if self.active and time.monotonic() >= self.end_at:
            condition = self.active
            self.active = None
            self.reply("DONE RUN " + condition)
        return len(self.lines)

    def read(self, n):
        result = bytes(self.lines[:n])
        del self.lines[:n]
        return result

    def write(self, payload):
        if self.unplugged:
            raise OSError("USB cable removed")
        for command in payload.decode().splitlines():
            self.commands.append(command)
            if command == "IDENTIFY":
                self.reply("WRONG_BOARD" if self.wrong_id else "AIMLAB_COMBINED_V7")
            elif command == "PING":
                self.reply("PONG")
            elif command in ("STOP", "!"):
                self.active = None
                self.reply("STOPPED: all outputs OFF")
            elif command == "STATUS" and not self.silent_status:
                mode = "PROTOCOL" if self.active else "IDLE"
                self.reply(f"Mode: {mode} | Peltier PWM=0 polarity=HOT | Motors PWM=0,0,0,0")
            elif command.startswith("RUN "):
                self.active = command.split()[1]
                self.end_at = time.monotonic() + .25
                if not self.suppress_ack:
                    self.reply("ACK RUN " + self.active)
        return len(payload)

    def reset_input_buffer(self):
        self.lines.clear()

    def close(self):
        pass


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.board = Board()
        self.port = SimpleNamespace(device="COM_TEST", vid=0x2341, pid=0x43, serial_number="TEST")
        self.link = UnoConnector(serial_factory=self.board.factory, port_provider=lambda: [self.port],
                                 boot_wait=.01, retry_s=.05)
        self.link.start()
        self.addCleanup(self.link.close)
        self.wait(lambda: self.link.snapshot()["state"] == "READY")

    def wait(self, predicate, timeout=2):
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            self.link.pulse()
            if predicate():
                return
            time.sleep(.01)
        self.fail("Timeout: " + str(self.link.snapshot()))

    def test_ack_done_and_off_confirmation(self):
        ticket = self.link.run("D", FastSettings())
        self.wait(lambda: bool(ticket.finished))
        self.assertTrue(ticket.sent <= ticket.ack <= ticket.done_received <= ticket.finished)
        self.assertEqual(self.link.snapshot()["state"], "READY")
        self.assertEqual(ticket.error, "")

    def test_unplug_reconnect_never_replays_run(self):
        ticket = self.link.run("D", FastSettings())
        self.wait(lambda: bool(ticket.ack))
        generation = self.link.snapshot()["generation"]
        self.board.unplugged = True
        self.wait(lambda: bool(ticket.error))
        self.board.unplugged = False
        self.wait(lambda: self.link.snapshot()["generation"] > generation)
        self.assertEqual(sum(c.startswith("RUN ") for c in self.board.commands), 1)
        self.assertEqual(self.link.snapshot()["state"], "READY")
        self.assertFalse(ticket.finished)

    def test_missing_ack_does_not_count_completion(self):
        self.board.suppress_ack = True
        ticket = self.link.run("C", FastSettings())
        self.wait(lambda: bool(ticket.error))
        self.assertFalse(ticket.finished)

    def test_status_timeout_even_with_pong(self):
        self.board.silent_status = True
        faults = self.link.snapshot()["fault_count"]
        self.wait(lambda: self.link.snapshot()["fault_count"] > faults)
        self.assertNotEqual(self.link.snapshot()["state"], "READY")

    def test_display_stall_stops_and_disconnects(self):
        faults = self.link.snapshot()["fault_count"]
        time.sleep(.6)  # deliberately do not pulse
        self.assertGreater(self.link.snapshot()["fault_count"], faults)
        self.assertTrue(any(c == "!" for c in self.board.commands))

    def test_operator_stop_invalidates_run(self):
        ticket = self.link.run("C", FastSettings())
        self.wait(lambda: bool(ticket.ack))
        self.link.stop()
        self.wait(lambda: bool(ticket.error) and self.link.snapshot()["state"] == "READY")
        self.assertFalse(ticket.finished)

    def test_second_command_rejected_and_idle_outputs_fault(self):
        ticket = self.link.run("C", FastSettings())
        with self.assertRaises(RuntimeError):
            self.link.run("D", FastSettings())
        self.wait(lambda: bool(ticket.finished))
        faults = self.link.snapshot()["fault_count"]
        self.board.reply("Mode: IDLE | Peltier PWM=100 polarity=HOT | Motors PWM=0,0,0,0")
        self.wait(lambda: self.link.snapshot()["fault_count"] > faults)

    def test_invalid_telemetry(self):
        with self.assertRaises(ValueError):
            parse_status("Mode: IDLE | Peltier PWM=999 polarity=HOT | Motors PWM=0,0,0,0")
        self.assertIsNone(parse_status("garbage"))

    def test_plateau_telemetry_mismatch_is_fault(self):
        # Test the parser/state check without a concurrent worker.
        self.link.close()
        ticket = RunTicket("B", Settings(), 1)
        ticket.sent = ticket.ack = time.monotonic()-1
        self.link.active = ticket
        with self.assertRaisesRegex(IOError, "Peltier PWM"):
            self.link._handle("Mode: PROTOCOL | Peltier PWM=0 polarity=HOT | Motors PWM=0,0,0,0", time.monotonic())

    def test_does_not_switch_to_another_usb_identity(self):
        other = SimpleNamespace(device="COM_OTHER", vid=0x2341, pid=0x43, serial_number="OTHER")
        self.link.ports = lambda: [other]
        self.assertEqual(list(self.link._candidates()), [])
        changed_port = SimpleNamespace(device="COM_NEW", vid=0x2341, pid=0x43, serial_number="TEST")
        self.link.ports = lambda: [changed_port]
        self.assertEqual(list(self.link._candidates())[0][0].device, "COM_NEW")

    def test_transient_port_scan_failure_recovers(self):
        self.board.unplugged = True
        faults = self.link.snapshot()["fault_count"]
        self.wait(lambda: self.link.snapshot()["fault_count"] > faults)
        self.board.unplugged = False
        calls = []
        def ports():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("Temporary enumeration failure")
            return [self.port]
        self.link.ports = ports
        self.wait(lambda: self.link.snapshot()["state"] == "READY")
        self.assertGreaterEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
