import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import update_all
import calculate_center_average as center_module
import calculate_daily_weather as daily_module
import calculate_health_risk as risk_module
from calculate_center_average import calculate_center_average
from calculate_daily_weather import calculate_daily_weather
from calculate_health_risk import (
    RESULT_COLUMNS,
    calculate_health_risk,
    classify_0_64,
    classify_65_plus,
)
from update_units import load_city


EXPECTED_UNIT_IDS = (
    "beijing_core",
    "beijing_110109",
    "beijing_110111",
    "beijing_110112",
    "beijing_110113",
    "beijing_110114",
    "beijing_110115",
    "beijing_110116",
    "beijing_110117",
    "beijing_110118",
    "beijing_110119",
)


def make_raw(unit_id, temperature=34.0):
    units, coordinates = load_city("beijing")
    weights = units[unit_id]
    times = pd.date_range("2026-07-01", periods=168, freq="h")
    return pd.DataFrame([
        {
            "update_time": "2026-07-01T00:00:00+08:00",
            "forecast_time": time,
            "key": point_key,
            "point_id": f"p{point:03d}",
            "temperature_c": temperature,
            "relative_humidity_pct": 50.0,
            "wind_speed_ms": 2.0,
            "area_weight": weights[point_key],
            "source": "Open-Meteo",
            "model": "ecmwf_ifs",
            "grid_latitude": coordinates[point_key][0],
            "grid_longitude": coordinates[point_key][1],
        }
        for time in times
        for point, point_key in enumerate(weights)
    ])


class BeijingPipelineTest(unittest.TestCase):
    def test_entry_imports_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "-c", "from scripts.update_all import run_beijing_forecast"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_recognizes_exactly_the_11_independent_units(self):
        self.assertEqual(update_all.get_beijing_unit_ids(), EXPECTED_UNIT_IDS)
        for invalid in ("beijing_urban", "beijing_other", "beijing_missing"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, "Unsupported Beijing unit_id"):
                    update_all.run_beijing_forecast(unit_id=invalid, raw=pd.DataFrame(), save=False)

    def test_core_result_matches_legacy_chain_column_for_column(self):
        raw = make_raw("beijing_core")
        legacy_hourly = calculate_center_average(raw)
        legacy_daily = calculate_daily_weather(legacy_hourly)
        expected = calculate_health_risk(legacy_daily)[RESULT_COLUMNS]

        actual = update_all.run_beijing_forecast(
            unit_id="beijing_core", raw=raw, save=False
        )
        pd.testing.assert_frame_equal(actual, expected)

    def test_other_district_runs_the_complete_shared_chain(self):
        raw = make_raw("beijing_110109")
        result = update_all.run_beijing_forecast(
            unit_id="beijing_110109", raw=raw, save=False
        )

        self.assertEqual(list(result.columns), [
            "update_time", "forecast_date", "tmean_c", "tmax_c",
            "rhmean_pct", "vmean_ms", "vapor_pressure_hpa", "at_c",
            "risk_0_64", "risk_65_plus", "hour_count", "is_complete_day",
            "source", "model",
        ])
        self.assertEqual(len(result), 7)
        self.assertTrue(result["is_complete_day"].all())
        self.assertTrue(result["tmean_c"].eq(34.0).all())
        self.assertTrue(result["tmax_c"].eq(34.0).all())
        self.assertTrue(result["rhmean_pct"].sub(50.0).abs().lt(1e-12).all())
        self.assertTrue(result["vmean_ms"].eq(2.0).all())
        self.assertAlmostEqual(result.iloc[0]["at_c"], 37.38, delta=0.05)
        self.assertTrue(result["risk_0_64"].eq("高风险").all())
        self.assertTrue(result["risk_65_plus"].eq("中风险").all())

    def test_existing_risk_threshold_boundaries_are_unchanged(self):
        self.assertEqual(classify_0_64(33.599), "未进入热效应风险分级")
        self.assertEqual(classify_0_64(33.6), "低风险")
        self.assertEqual(classify_0_64(35.2), "中风险")
        self.assertEqual(classify_0_64(37.2), "高风险")
        self.assertEqual(classify_65_plus(34.499), "未进入热效应风险分级")
        self.assertEqual(classify_65_plus(34.5), "低风险")
        self.assertEqual(classify_65_plus(35.9), "中风险")
        self.assertEqual(classify_65_plus(37.6), "高风险")

    def test_core_save_writes_unit_outputs_and_legacy_aliases(self):
        raw = make_raw("beijing_core")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_hourly = root / "current/beijing_center_forecast_hourly.csv"
            legacy_daily = root / "current/beijing_center_forecast_daily.csv"
            legacy_risk = root / "processed/beijing_center_health_risk.csv"
            legacy_hourly.parent.mkdir(parents=True)
            legacy_risk.parent.mkdir(parents=True)
            with (
                patch.object(update_all, "ROOT", root),
                patch.object(center_module, "HOURLY_OUTPUT", legacy_hourly),
                patch.object(daily_module, "DAILY", legacy_daily),
                patch.object(risk_module, "OUTPUT_FILE", legacy_risk),
            ):
                update_all.run_beijing_forecast(
                    unit_id="beijing_core", raw=raw, save=True
                )

            expected = (
                root / "data/current/units/beijing_core_hourly.csv",
                root / "data/current/units/beijing_core_daily.csv",
                root / "data/processed/units/beijing_core_health_risk.csv",
                legacy_hourly,
                legacy_daily,
                legacy_risk,
            )
            self.assertTrue(all(path.is_file() for path in expected))


if __name__ == "__main__":
    unittest.main()
