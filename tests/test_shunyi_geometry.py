import json
import unittest
import tempfile
import shutil
import sys
from pathlib import Path

from shapely.geometry import shape
from shapely.validation import explain_validity
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_spatial import build_units, calculate_points


class ShunyiGeometryTest(unittest.TestCase):
    def test_builder_rejects_invalid_source_with_district_code(self):
        with tempfile.TemporaryDirectory() as directory:
            shutil.copytree(ROOT / 'data/boundary_sources', directory, dirs_exist_ok=True)
            path = Path(directory) / '110000.json'
            data = json.loads(path.read_text(encoding='gb18030'))
            feature = next(f for f in data['features'] if f['properties']['adcode'] == 110113)
            feature['geometry'] = {'type': 'Polygon', 'coordinates': [[[116,40],[117,41],[117,40],[116,41],[116,40]]]}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding='gb18030')
            with self.assertRaisesRegex(ValueError, '110113.*invalid geometry'):
                build_units(directory)

    def test_points_reject_invalid_geometry(self):
        geometry = shape({'type': 'Polygon', 'coordinates': [[[116,40],[117,41],[117,40],[116,41],[116,40]]]})
        with self.assertRaisesRegex(ValueError, 'invalid geometry'):
            calculate_points(geometry)

    def test_source_shunyi_is_valid(self):
        data = json.loads((ROOT / 'data/boundary_sources/110000.json').read_text(encoding='gb18030'))
        geometry = shape(next(f for f in data['features'] if f['properties']['adcode'] == 110113)['geometry'])
        self.assertTrue(geometry.is_valid, explain_validity(geometry))

    def test_repair_preserves_both_original_faces_and_their_hole(self):
        original = shape(json.loads((ROOT / 'tests/fixtures/shunyi_original.geojson').read_text(encoding='utf-8'))['geometry'])
        self.assertTrue(all(part.is_valid for part in original.geoms))
        self.assertEqual(original.geoms[0].intersection(original.geoms[1]).area, 0)
        reference = unary_union(original.geoms)
        data = json.loads((ROOT / 'data/boundary_sources/110000.json').read_text(encoding='gb18030'))
        fixed = shape(next(f for f in data['features'] if f['properties']['adcode'] == 110113)['geometry'])
        self.assertTrue(fixed.equals(reference))
        self.assertEqual(len(fixed.geoms), 1)
        self.assertEqual(len(fixed.geoms[0].interiors), 1)
        for part in original.geoms:
            self.assertEqual(part.difference(fixed).area, 0)

    def test_generated_shunyi_is_valid_and_matches_source(self):
        data = json.loads((ROOT / 'data/boundary_sources/110000.json').read_text(encoding='gb18030'))
        source = shape(next(f for f in data['features'] if f['properties']['adcode'] == 110113)['geometry'])
        generated = shape(json.loads((ROOT / 'data/static/units/beijing_110113.geojson').read_text(encoding='utf-8'))['geometry'])
        self.assertTrue(generated.is_valid, explain_validity(generated))
        self.assertTrue(source.equals(generated))
