import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update_units import daily_from_hourly, weighted_hourly, coordinate_distance_m


class UnitProcessingTest(unittest.TestCase):
    def test_shared_grid_values_make_separate_unit_average(self):
        times = pd.date_range("2026-07-01", periods=168, freq="h")
        raw = pd.DataFrame([
            {"forecast_time": time, "key": key, "temperature_c": temp,
             "relative_humidity_pct": 50, "wind_speed_ms": 2}
            for time in times for key, temp in (("a", 30), ("b", 34))
        ])
        hourly = weighted_hourly(raw, {"a": 0.25, "b": 0.75}, "2026-07-01T00:00:00+08:00")
        daily = daily_from_hourly(hourly)
        self.assertEqual(len(hourly), 168)
        self.assertAlmostEqual(daily.iloc[0]["tmean_c"], 33)
        self.assertEqual(daily.iloc[0]["hour_count"], 24)
        self.assertTrue(daily.iloc[0]["is_complete_day"])

    def test_rejects_grid_shift(self):
        self.assertLess(coordinate_distance_m(39, 116, 39.000001, 116), 2)
        self.assertGreater(coordinate_distance_m(39, 116, 39.01, 116), 1000)


if __name__ == "__main__":
    unittest.main()
