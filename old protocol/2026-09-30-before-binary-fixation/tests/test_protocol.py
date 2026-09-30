import unittest
from collections import Counter
from aimlab.protocol import Settings, sequence, ROWS


class ProtocolTests(unittest.TestCase):
    def test_exact_existing_design(self):
        trials = sequence(42)
        self.assertEqual(len(trials), 160)
        self.assertEqual(Counter(t["condition"] for t in trials), dict.fromkeys("ABCD", 40))
        for block in range(1, 6):
            letters = "".join(t["condition"] for t in trials if t["block"] == block)
            self.assertEqual(letters, "ABD CBCAD CDBA DACB".replace(" ", "")*2)
        # Each directed pair occurs once within the four Latin rows.
        pairs = Counter(a+b for row in ROWS for a,b in zip(row,row[1:]))
        self.assertEqual(len(pairs), 12)
        self.assertTrue(all(n == 1 for n in pairs.values()))

    def test_fixations_are_reproducible(self):
        self.assertEqual(sequence(42), sequence(42))
        self.assertNotEqual(sequence(42), sequence(43))
        self.assertTrue(all(3 <= t["fixation_s"] <= 4.5 for t in sequence(42)))

    def test_settings_and_existing_firmware_timing(self):
        s = Settings(146, 970)
        self.assertEqual(s.command("D"), "RUN D H 183 146 146 146 146 970 4000")
        self.assertEqual(s.duration_s("D"), 4.97)
        self.assertEqual(s.duration_s("C"), 4)
        self.assertEqual(s.duration_s("B"), 5)
        for kwargs in ({"motor_pwm": 256}, {"lead_ms": -1}, {"lead_ms": 2001},
                       {"polarity": "C"}, {"motion_ms": 4050}, {"motor_pwm": True}):
            with self.assertRaises(ValueError):
                Settings(**kwargs)


if __name__ == "__main__":
    unittest.main()
