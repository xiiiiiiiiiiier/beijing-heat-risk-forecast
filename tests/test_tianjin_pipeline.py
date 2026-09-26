import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_all
import update_units
from calculate_daily_weather import calculate_daily_weather
from calculate_health_risk import RESULT_COLUMNS, calculate_health_risk
from update_units import daily_from_hourly, load_city


EXPECTED_UNIT_IDS = (
    "tianjin_core",
    "tianjin_120110",
    "tianjin_120111",
    "tianjin_120112",
    "tianjin_120113",
    "tianjin_120114",
    "tianjin_120115",
    "tianjin_120116",
    "tianjin_120117",
    "tianjin_120118",
    "tianjin_120119",
)


def make_raw(unit_id, temperature=34.0):
    units, coordinates = load_city("tianjin")
    weights = units[unit_id]
    times = pd.date_range("2026-07-01", periods=168, freq="h")
    return pd.DataFrame([
        {
            "update_time": "2026-07-01T00:00:00+08:00",
            "forecast_time": time,
            "key": point_key,
            "temperature_c": temperature,
            "relative_humidity_pct": 50.0,
            "wind_speed_ms": 2.0,
            "source": "Open-Meteo",
            "model": "ecmwf_ifs",
            "grid_latitude": coordinates[point_key][0],
            "grid_longitude": coordinates[point_key][1],
        }
        for time in times
        for point_key in weights
    ])


class TianjinPipelineTest(unittest.TestCase):
    def test_entry_imports_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "-c", "from scripts.update_all import run_tianjin_forecast"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_recognizes_exactly_the_11_at_units(self):
        self.assertEqual(update_all.get_tianjin_unit_ids(), EXPECTED_UNIT_IDS)
        for invalid in ("tianjin_urban", "tianjin_other", "tianjin_missing"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Unsupported Tianjin unit_id"):
                    update_all.run_tianjin_forecast(
                        unit_id=invalid, raw=pd.DataFrame(), save=False
                    )

    def test_core_runs_hourly_daily_at_and_both_age_risks(self):
        result = update_all.run_tianjin_forecast(
            unit_id="tianjin_core", raw=make_raw("tianjin_core"), save=False
        )
        self.assertEqual(list(result.columns), RESULT_COLUMNS)
        self.assertEqual(len(result), 7)
        self.assertTrue(result["is_complete_day"].all())
        self.assertTrue(result["at_c"].notna().all())
        self.assertTrue(result["risk_0_64"].eq("高风险").all())
        self.assertTrue(result["risk_65_plus"].eq("中风险").all())

    def test_binhai_runs_through_the_same_entry_with_54_points(self):
        result = update_all.run_tianjin_forecast(
            unit_id="tianjin_120116", raw=make_raw("tianjin_120116"), save=False
        )
        self.assertEqual(len(result), 7)
        self.assertTrue(result["tmean_c"].eq(34.0).all())
        self.assertTrue(result["at_c"].notna().all())

    def test_formal_daily_chain_reproduces_committed_tianjin_core_result(self):
        hourly = pd.read_csv(ROOT / "data/current/units/tianjin_core_hourly.csv")
        expected = pd.read_csv(
            ROOT / "data/processed/units/tianjin_core_health_risk.csv"
        )[RESULT_COLUMNS]
        actual = calculate_health_risk(calculate_daily_weather(hourly))[RESULT_COLUMNS]
        actual["forecast_date"] = actual["forecast_date"].astype(str)
        pd.testing.assert_frame_equal(actual, expected, check_dtype=False, atol=1e-12)

    def test_batch_daily_compatibility_uses_the_formal_daily_result(self):
        hourly = pd.read_csv(ROOT / "data/current/units/tianjin_core_hourly.csv")
        pd.testing.assert_frame_equal(
            daily_from_hourly(hourly), calculate_daily_weather(hourly)
        )

    def test_existing_batch_cli_still_dispatches_tianjin(self):
        with (
            patch.object(sys, "argv", ["update_units.py", "--city", "tianjin"]),
            patch.object(update_units, "update_city") as update_city,
        ):
            self.assertEqual(update_units.main(), 0)
        update_city.assert_called_once_with("tianjin")


if __name__ == "__main__":
    unittest.main()
