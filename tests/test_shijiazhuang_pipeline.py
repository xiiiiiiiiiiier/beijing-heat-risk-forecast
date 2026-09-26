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
from update_units import load_city


EXPECTED_UNIT_IDS = (
    "shijiazhuang_core",
    "shijiazhuang_130107",
    "shijiazhuang_130109",
    "shijiazhuang_130110",
    "shijiazhuang_130111",
)


def make_raw(unit_id, temperature=34.0):
    units, coordinates = load_city("shijiazhuang")
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


class ShijiazhuangPipelineTest(unittest.TestCase):
    def test_entry_imports_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "-c", "from scripts.update_all import run_shijiazhuang_forecast"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_recognizes_exactly_the_5_at_units(self):
        self.assertEqual(update_all.get_shijiazhuang_unit_ids(), EXPECTED_UNIT_IDS)
        for invalid in (
            "shijiazhuang_urban",
            "shijiazhuang_other",
            "shijiazhuang_missing",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(
                    ValueError, "Unsupported Shijiazhuang unit_id"
                ):
                    update_all.run_shijiazhuang_forecast(
                        unit_id=invalid, raw=pd.DataFrame(), save=False
                    )

    def test_core_runs_hourly_daily_at_and_both_age_risks(self):
        result = update_all.run_shijiazhuang_forecast(
            unit_id="shijiazhuang_core",
            raw=make_raw("shijiazhuang_core"),
            save=False,
        )
        self.assertEqual(list(result.columns), RESULT_COLUMNS)
        self.assertEqual(len(result), 7)
        self.assertTrue(result["is_complete_day"].all())
        self.assertTrue(result["at_c"].notna().all())
        self.assertTrue(result["risk_0_64"].eq("高风险").all())
        self.assertTrue(result["risk_65_plus"].eq("中风险").all())

    def test_jingxing_mining_runs_through_the_same_entry_with_6_points(self):
        result = update_all.run_shijiazhuang_forecast(
            unit_id="shijiazhuang_130107",
            raw=make_raw("shijiazhuang_130107"),
            save=False,
        )
        self.assertEqual(len(result), 7)
        self.assertTrue(result["tmean_c"].eq(34.0).all())
        self.assertTrue(result["at_c"].notna().all())

    def test_formal_chain_reproduces_committed_core_results(self):
        hourly = pd.read_csv(ROOT / "data/current/units/shijiazhuang_core_hourly.csv")
        expected_daily = pd.read_csv(
            ROOT / "data/current/units/shijiazhuang_core_daily.csv"
        )
        expected_risk = pd.read_csv(
            ROOT / "data/processed/units/shijiazhuang_core_health_risk.csv"
        )[RESULT_COLUMNS]

        actual_daily = calculate_daily_weather(hourly)
        actual_risk = calculate_health_risk(actual_daily)[RESULT_COLUMNS]
        actual_daily["forecast_date"] = actual_daily["forecast_date"].astype(str)
        actual_risk["forecast_date"] = actual_risk["forecast_date"].astype(str)

        pd.testing.assert_frame_equal(
            actual_daily, expected_daily, check_dtype=False, atol=1e-12
        )
        pd.testing.assert_frame_equal(
            actual_risk, expected_risk, check_dtype=False, atol=1e-12
        )

    def test_existing_batch_cli_still_dispatches_shijiazhuang(self):
        with (
            patch.object(
                sys, "argv", ["update_units.py", "--city", "shijiazhuang"]
            ),
            patch.object(update_units, "update_city") as update_city,
        ):
            self.assertEqual(update_units.main(), 0)
        update_city.assert_called_once_with("shijiazhuang")


if __name__ == "__main__":
    unittest.main()
