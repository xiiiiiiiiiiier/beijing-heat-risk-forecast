import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update_units import daily_from_hourly, weighted_hourly, coordinate_distance_m, fetch_city


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

    def test_weighted_hourly_parses_api_timestamp_strings(self):
        times = pd.date_range("2026-07-01", periods=168, freq="h")
        raw = pd.DataFrame([
            {"forecast_time": time.strftime("%Y-%m-%dT%H:%M"), "key": key,
             "temperature_c": temp, "relative_humidity_pct": 50, "wind_speed_ms": 2}
            for time in times for key, temp in (("a", 30), ("b", 34))
        ])
        hourly = weighted_hourly(raw, {"a": 0.25, "b": 0.75}, "2026-07-01T00:00:00+08:00")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(hourly["forecast_time"]))

    def test_rejects_grid_shift(self):
        self.assertLess(coordinate_distance_m(39, 116, 39.000001, 116), 2)
        self.assertGreater(coordinate_distance_m(39, 116, 39.01, 116), 1000)

    def test_retries_temporary_http_errors_before_accepting_forecast(self):
        class Reply:
            def __init__(self, status):
                self.status_code = status
                self.headers = {}

            def raise_for_status(self):
                if self.status_code != 200:
                    raise requests.exceptions.HTTPError(str(self.status_code))

            def json(self):
                times = pd.date_range("2026-07-01", periods=168, freq="h")
                return {"latitude": 39, "longitude": 116, "hourly": {
                    "time": [x.strftime("%Y-%m-%dT%H:%M") for x in times],
                    "temperature_2m": [30] * 168,
                    "relative_humidity_2m": [50] * 168,
                    "wind_speed_10m": [2] * 168,
                }}

        for status in (408, 429, 500, 502, 503, 504):
            with self.subTest(status=status), \
                 patch("update_units._requested_points", 0), \
                 patch("update_units.requests.get", side_effect=[Reply(status), Reply(200)]) as get, \
                 patch("update_units.time.sleep") as sleep:
                result = fetch_city({"39.0000000000,116.0000000000": (39, 116)}, "run")
                self.assertEqual(len(result), 168)
                self.assertEqual(get.call_count, 2)
                sleep.assert_called_once_with(61 if status == 429 else 15)

    def test_persistent_http_errors_fail_without_infinite_retry(self):
        from unittest.mock import Mock
        for status, attempts in ((503, 3), (400, 1), (401, 1), (403, 1), (404, 1)):
            response = Mock(status_code=status)
            response.raise_for_status.side_effect = requests.exceptions.HTTPError(str(status))
            with self.subTest(status=status), \
                 patch("update_units._requested_points", 0), \
                 patch("update_units.requests.get", return_value=response) as get, \
                 patch("update_units.time.sleep") as sleep:
                with self.assertRaises(requests.exceptions.HTTPError):
                    fetch_city({"39.0000000000,116.0000000000": (39, 116)}, "run")
                self.assertEqual(get.call_count, attempts)
                self.assertEqual(sleep.call_count, attempts - 1)
                response.json.assert_not_called()

    def test_retries_network_timeout(self):
        with patch("update_units.requests.get", side_effect=requests.exceptions.ReadTimeout) as get, \
             patch("update_units.time.sleep") as sleep:
            with self.assertRaises(requests.exceptions.ReadTimeout):
                fetch_city({"39.0000000000,116.0000000000": (39, 116)}, "run")
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
