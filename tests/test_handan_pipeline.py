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
from calculate_health_risk import RESULT_COLUMNS
from update_units import load_city


EXPECTED_UNIT_IDS = (
    "handan_core",
    "handan_130406",
    "handan_130407",
    "handan_130408",
)


def make_raw(unit_id, temperature=34.0):
    units, coordinates = load_city("handan")
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


def raw_from_weighted_hourly(unit_id, hourly):
    units, coordinates = load_city("handan")
    return pd.DataFrame([
        {
            "update_time": row.update_time,
            "forecast_time": row.forecast_time,
            "key": point_key,
            "temperature_c": row.temperature_c,
            "relative_humidity_pct": row.relative_humidity_pct,
            "wind_speed_ms": row.wind_speed_ms,
            "source": row.source,
            "model": row.model,
            "grid_latitude": coordinates[point_key][0],
            "grid_longitude": coordinates[point_key][1],
        }
        for row in hourly.itertuples(index=False)
        for point_key in units[unit_id]
    ])


class HandanPipelineTest(unittest.TestCase):
    def test_entry_imports_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "-c", "from scripts.update_all import run_handan_forecast"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_recognizes_exactly_the_4_at_units(self):
        self.assertEqual(update_all.get_handan_unit_ids(), EXPECTED_UNIT_IDS)
        for invalid in ("handan_urban", "handan_other", "handan_missing"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Unsupported Handan unit_id"):
                    update_all.run_handan_forecast(
                        unit_id=invalid, raw=pd.DataFrame(), save=False
                    )

    def test_core_runs_hourly_daily_at_and_both_age_risks(self):
        result = update_all.run_handan_forecast(
            unit_id="handan_core", raw=make_raw("handan_core"), save=False
        )
        self.assertEqual(list(result.columns), RESULT_COLUMNS)
        self.assertEqual(len(result), 7)
        self.assertTrue(result["is_complete_day"].all())
        self.assertTrue(result["at_c"].notna().all())
        self.assertTrue(result["risk_0_64"].eq("高风险").all())
        self.assertTrue(result["risk_65_plus"].eq("中风险").all())

    def test_fengfeng_runs_through_the_same_entry_with_11_points(self):
        raw = make_raw("handan_130406")
        self.assertEqual(len(raw), 168 * 11)
        result = update_all.run_handan_forecast(
            unit_id="handan_130406", raw=raw, save=False
        )
        self.assertEqual(len(result), 7)
        self.assertTrue(result["tmean_c"].eq(34.0).all())
        self.assertTrue(result["at_c"].notna().all())

    def test_new_entry_reproduces_committed_core_results(self):
        hourly = pd.read_csv(ROOT / "data/current/units/handan_core_hourly.csv")
        expected_daily = pd.read_csv(
            ROOT / "data/current/units/handan_core_daily.csv"
        )
        expected_risk = pd.read_csv(
            ROOT / "data/processed/units/handan_core_health_risk.csv"
        )[RESULT_COLUMNS]

        actual_risk = update_all.run_handan_forecast(
            unit_id="handan_core",
            raw=raw_from_weighted_hourly("handan_core", hourly),
            save=False,
        )
        actual_daily = actual_risk[expected_daily.columns]
        actual_daily["forecast_date"] = actual_daily["forecast_date"].astype(str)
        actual_risk["forecast_date"] = actual_risk["forecast_date"].astype(str)

        pd.testing.assert_frame_equal(
            actual_daily, expected_daily, check_dtype=False, atol=1e-12
        )
        pd.testing.assert_frame_equal(
            actual_risk, expected_risk, check_dtype=False, atol=1e-12
        )

    def test_existing_batch_cli_still_dispatches_handan(self):
        with (
            patch.object(sys, "argv", ["update_units.py", "--city", "handan"]),
            patch.object(update_units, "update_city") as update_city,
        ):
            self.assertEqual(update_units.main(), 0)
        update_city.assert_called_once_with("handan")


if __name__ == "__main__":
    unittest.main()
