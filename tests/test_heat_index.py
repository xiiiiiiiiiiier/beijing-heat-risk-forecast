import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from heat_index import heat_index_c, heat_index_tables, classify


class HeatIndexTest(unittest.TestCase):
    def test_noaa_examples_and_ecmwf_boundaries(self):
        self.assertAlmostEqual(heat_index_c(30, 70), 35.0, delta=1)
        self.assertAlmostEqual(heat_index_c(20, 50), 19.4, delta=2)
        self.assertEqual(classify(26.69)[0], "低于注意级别")
        self.assertEqual(classify(26.7)[0], "注意")
        self.assertEqual(classify(32.2)[0], "极度谨慎")
        self.assertEqual(classify(39.4)[0], "危险")
        self.assertEqual(classify(51.1)[0], "极端危险")

    def test_daily_uses_hourly_peak_and_marks_incomplete_day(self):
        times = pd.date_range("2026-07-01", periods=25, freq="h")
        hourly = pd.DataFrame({"update_time": "run", "forecast_time": times,
                               "temperature_c": [25] * 24 + [30],
                               "relative_humidity_pct": [50] * 24 + [70],
                               "source": "Open-Meteo", "model": "ecmwf_ifs"})
        hourly_out, daily = heat_index_tables(hourly)
        self.assertEqual(len(hourly_out), 25)
        self.assertEqual(len(daily), 2)
        self.assertTrue(daily.iloc[0].is_complete_day)
        self.assertFalse(daily.iloc[1].is_complete_day)
        self.assertEqual(daily.iloc[1].effect_on_body, "不完整日，不进入正式分级")
        self.assertAlmostEqual(daily.iloc[1].hi_max_c, hourly_out.iloc[24].hi_c)


if __name__ == "__main__":
    unittest.main()
