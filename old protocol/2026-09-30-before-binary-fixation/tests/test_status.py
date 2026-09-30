import json
from pathlib import Path
import statistics
import unittest
from aimlab.status import connection_is_fresh
from aimlab.protocol import Settings

class StatusTests(unittest.TestCase):
    def test_fresh_stale_disconnected_and_no_condition_leak(self):
        snapshot = {"state": "READY", "telemetry": {"thermal": 0}, "status_at": 10}
        idle = connection_is_fresh(snapshot, 10.1)
        self.assertTrue(idle)
        snapshot.update(state="RUNNING", telemetry={"thermal": 183})
        self.assertEqual(connection_is_fresh(snapshot, 10.1), idle)
        self.assertFalse(connection_is_fresh(snapshot, 11))
        snapshot["state"] = "DISCONNECTED"
        self.assertFalse(connection_is_fresh(snapshot, 11))

    def test_defaults_match_six_participant_means(self):
        root = Path(__file__).resolve().parents[1]
        rows = json.loads((root/'reference/participant-analysis/participant-mapping.json').read_text())
        config = json.loads((root/'study.json').read_text())
        motor = round(statistics.mean(row['settings']['masterPwm'] for row in rows))
        thermal = round(statistics.mean(row['settings']['thermalPwm'] for row in rows))
        self.assertEqual((motor, thermal), (189,183))
        self.assertEqual((config['initial_motor_pwm'], config['thermal_pwm']), (motor, thermal))
        self.assertEqual((Settings().motor_pwm, Settings().thermal_pwm), (motor, thermal))
