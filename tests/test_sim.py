import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))
import sim


class JerkCalibrationTests(unittest.TestCase):
    def test_severe_legitimate_braking_has_no_false_alarm_or_collision(self):
        rows = [
            sim.run("CA_full", "L2_legit_brake", seed)
            for seed in range(1, 21)
        ]
        self.assertEqual(sum(row["collision"] for row in rows), 0)
        self.assertEqual(sum(row["first_det"] is not None for row in rows), 0)
        self.assertEqual(sum(row["rev"] is not None for row in rows), 0)

    def test_false_acceleration_attacks_remain_detected(self):
        for scenario in ("A1_false_brake", "A2_false_accel", "A3_stealth_ramp"):
            with self.subTest(scenario=scenario):
                rows = [
                    sim.run("CA_full", scenario, seed)
                    for seed in range(1, 21)
                ]
                self.assertEqual(sum(row["first_det"] is not None for row in rows), 20)
                self.assertEqual(sum(row["collision"] for row in rows), 0)


if __name__ == "__main__":
    unittest.main()
