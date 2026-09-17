import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_spatial import build_units, calculate_points


class SpatialTest(unittest.TestCase):
    def test_all_urban_districts_are_units(self):
        units = build_units(ROOT / "data/boundary_sources")
        self.assertEqual(len(units), 64)
        self.assertIn("beijing_110101", units)
        self.assertIn("baoding_130602", units)
        self.assertIn("beijing_110112", units)
        self.assertNotIn("shijiazhuang_130121", units)

    def test_beijing_core_reproduces_existing_points(self):
        units = build_units(ROOT / "data/boundary_sources")
        core = units["beijing_core"]
        points = calculate_points(core["geometry"])
        old = __import__("pandas").read_csv(ROOT / "data/static/forecast_points.csv")
        self.assertEqual(len(points), 30)
        self.assertEqual(
            {(round(p["latitude"], 6), round(p["longitude"], 6)) for p in points},
            {(round(p.latitude, 6), round(p.longitude, 6)) for p in old.itertuples()},
        )
        self.assertAlmostEqual(sum(p["area_weight"] for p in points), 1, places=8)
        self.assertAlmostEqual(sum(p["intersect_area_km2"] for p in points), 1376.496, places=2)


if __name__ == "__main__":
    unittest.main()
