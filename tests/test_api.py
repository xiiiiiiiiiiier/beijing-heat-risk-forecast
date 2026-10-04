import csv
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import BEIJING, ROOT, create_app


class ForecastAPITest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def test_all_45_units_preserve_published_values(self):
        cities = self.client.get('/api/v1/cities').json()
        self.assertEqual(len(cities), 6)
        self.assertEqual(sum(c['unit_count'] for c in cities), 45)
        for city in cities:
            for unit in self.client.get(f"/api/v1/cities/{city['city']}/units").json():
                uid = unit['unit_id']
                routes = [('hourly', 'current', 'hourly'), ('daily', 'current', 'daily')]
                routes += ([('heat-index/hourly', 'processed', 'heat_index_hourly'),
                            ('heat-index/daily', 'processed', 'heat_index_daily')]
                           if uid.endswith('_urban') else [('health-risk', 'processed', 'health_risk')])
                for endpoint, folder, suffix in routes:
                    with self.subTest(unit=uid, endpoint=endpoint):
                        response = self.client.get(f'/api/v1/units/{uid}/{endpoint}')
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertEqual(result['timezone'], 'Asia/Shanghai')
                        with (ROOT / 'data' / folder / 'units' / f'{uid}_{suffix}.csv').open(encoding='utf-8-sig') as f:
                            expected = list(csv.DictReader(f))
                        self.assertEqual(len(result['rows']), len(expected))
                        for actual, original in zip(result['rows'], expected):
                            for key, value in actual.items():
                                if key in ('update_time', 'forecast_time', 'hi_max_time'):
                                    t = datetime.fromisoformat(original[key])
                                    t = t.replace(tzinfo=BEIJING) if t.tzinfo is None else t.astimezone(BEIJING)
                                    self.assertEqual(datetime.fromisoformat(value), t)
                                elif isinstance(value, bool):
                                    self.assertEqual(value, original[key] == 'True')
                                elif isinstance(value, (int, float)):
                                    self.assertAlmostEqual(value, float(original[key]), places=12)
                                else:
                                    self.assertEqual(value, original[key] or None)

    def test_unknown_and_unsupported_requests(self):
        for url, code in [('/api/v1/cities/unknown/units', 404),
                          ('/api/v1/units/beijing_other/hourly', 404),
                          ('/api/v1/units/beijing_urban/health-risk', 422),
                          ('/api/v1/units/beijing_core/heat-index/daily', 422),
                          ('/api/v1/units/..%2F..%2FREADME/hourly', 404)]:
            self.assertEqual(self.client.get(url).status_code, code)

    def test_health_and_openapi(self):
        self.assertEqual(self.client.get('/health').json(), {'status': 'ok'})
        self.assertEqual(self.client.get('/docs').status_code, 200)
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/v1/units/{unit_id}/health-risk', schema['paths'])

    def test_complete_snapshot_and_revision(self):
        with patch.dict('os.environ', {'RENDER_GIT_COMMIT': 'abc123', 'VALIDATE_SNAPSHOT_ON_START': '1'}):
            with TestClient(create_app()) as client:
                response = client.get('/api/v1/status')
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['file_count'], 141)
                self.assertEqual(response.json()['unit_count'], 45)
                self.assertEqual(response.json()['snapshot_revision'], 'abc123')
                self.assertEqual(len(response.json()['cities']), 6)
                self.assertEqual(client.get('/api/v1/units/beijing_core/daily').json()['snapshot_revision'], 'abc123')

    def test_mixed_snapshot_cannot_start(self):
        from fastapi import HTTPException
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'data'
            for folder in ('static/units', 'current/units', 'processed/units'):
                shutil.copytree(ROOT / 'data' / folder, root / folder)
            path = root / 'processed/units/beijing_core_health_risk.csv'
            original = path.read_text(encoding='utf-8-sig')
            first_time = original.splitlines()[1].split(',')[0]
            wrong_time = (datetime.fromisoformat(first_time) - timedelta(hours=6)).isoformat()
            path.write_text(original.replace(first_time, wrong_time), encoding='utf-8')
            self.assertEqual(TestClient(create_app(root)).get('/api/v1/status').status_code, 503)
            with patch.dict('os.environ', {'VALIDATE_SNAPSHOT_ON_START': '1'}):
                with self.assertRaises(HTTPException):
                    with TestClient(create_app(root)):
                        pass
            # Fixing the candidate restores readiness; source data was never changed.
            path.write_text(original, encoding='utf-8')
            self.assertEqual(TestClient(create_app(root)).get('/api/v1/status').status_code, 200)

    def test_truncated_daily_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'data'
            for folder in ('static/units', 'current/units', 'processed/units'):
                shutil.copytree(ROOT / 'data' / folder, root / folder)
            path = root / 'current/units/beijing_core_daily.csv'
            path.write_text('\n'.join(path.read_text(encoding='utf-8-sig').splitlines()[:2]), encoding='utf-8')
            self.assertEqual(TestClient(create_app(root)).get('/api/v1/status').status_code, 503)

    def test_cors_allows_only_configured_frontend(self):
        with patch.dict('os.environ', {'CORS_ORIGINS': 'https://example.vercel.app'}):
            client = TestClient(create_app())
            for origin, allowed in [('https://example.vercel.app', True), ('https://other.example', False)]:
                response = client.get('/health', headers={'Origin': origin})
                self.assertEqual('access-control-allow-origin' in response.headers, allowed)

    def test_bad_or_missing_data_is_503(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = TestClient(create_app(root))
            self.assertEqual(client.get('/api/v1/cities').status_code, 503)
            (root / 'static/units').mkdir(parents=True)
            shutil.copy(ROOT / 'data/static/units/manifest.json', root / 'static/units/manifest.json')
            url = '/api/v1/units/beijing_core/hourly'
            self.assertEqual(client.get(url).status_code, 503)
            (root / 'current/units').mkdir(parents=True)
            path = root / 'current/units/beijing_core_hourly.csv'
            original = (ROOT / 'data/current/units/beijing_core_hourly.csv').read_text(encoding='utf-8-sig')
            for value in ('', 'bad,header\n1,2', original.replace('Open-Meteo', ''),
                          original + original.splitlines()[1] + '\n',
                          '\n'.join(original.splitlines()[:2]),
                          original.splitlines()[0] + '\n,'):
                path.write_text(value, encoding='utf-8')
                self.assertEqual(client.get(url).status_code, 503)

    def test_stale_and_incomplete_day_remain_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'static/units').mkdir(parents=True)
            shutil.copy(ROOT / 'data/static/units/manifest.json', root / 'static/units/manifest.json')
            (root / 'processed/units').mkdir(parents=True)
            with (ROOT / 'data/processed/units/beijing_core_health_risk.csv').open(encoding='utf-8-sig') as f:
                row = next(csv.DictReader(f))
            row.update(update_time=(datetime.now(BEIJING) - timedelta(days=2)).isoformat(),
                       hour_count='12', is_complete_day='False', at_c='', vapor_pressure_hpa='',
                       risk_0_64='不完整日，不进入正式分级', risk_65_plus='不完整日，不进入正式分级')
            path = root / 'processed/units/beijing_core_health_risk.csv'

            def save():
                with path.open('w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=row.keys())
                    writer.writeheader()
                    writer.writerow(row)

            save()
            client = TestClient(create_app(root))
            url = '/api/v1/units/beijing_core/health-risk'
            result = client.get(url).json()
            self.assertTrue(result['is_stale'])
            self.assertIsNone(result['rows'][0]['at_c'])
            self.assertFalse(result['rows'][0]['is_complete_day'])
            self.assertEqual(result['rows'][0]['risk_65_plus'], row['risk_65_plus'])
            row['at_c'] = 'NaN'
            save()
            self.assertEqual(client.get(url).status_code, 503)
            row['at_c'] = ''
            row['is_complete_day'] = 'True'
            save()
            self.assertEqual(client.get(url).status_code, 503)


if __name__ == '__main__':
    unittest.main()
