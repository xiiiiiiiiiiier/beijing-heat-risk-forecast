"""Recompute every Beijing output from a saved input; isolate weight-only effects.

Writes an audit below --out. Does not modify repository forecast files or fetch data.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from update_units import key, load_city, weighted_hourly
from calculate_daily_weather import calculate_daily_weather
from calculate_health_risk import calculate_health_risk
from heat_index import heat_index_tables
from api import app


def compare_frames(actual, expected, name):
    assert set(actual.columns) == set(expected.columns), f'{name}: columns'
    expected = expected[list(actual.columns)]
    assert len(actual) == len(expected), f'{name}: row count'
    numeric = {}
    for column in expected.columns:
        if pd.api.types.is_numeric_dtype(expected[column]) and expected[column].dtype != bool:
            left = pd.to_numeric(actual[column], errors='raise').to_numpy(dtype=float)
            right = expected[column].to_numpy(dtype=float)
            assert np.isfinite(left).all() and np.isfinite(right).all(), f'{name}: {column} missing/nonfinite'
            delta = float(np.max(np.abs(left-right)))
            assert np.allclose(left, right, rtol=0, atol=1e-10), f'{name}: {column} differs {delta}'
            numeric[column] = delta
        else:
            # CSVs contain dates/times as strings; parse expected serializer format.
            left = actual[column].astype(str).tolist()
            right = expected[column].astype(str).tolist()
            assert left == right, f'{name}: {column} differs'
    return numeric


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--before-ref', default='196f7cee31b2a5a787f6f290823120eb8c80b9d7')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = pd.read_csv(args.input)
    assert raw.update_time.nunique() == 1
    assert raw.model.eq('ecmwf_ifs').all() and raw.source.eq('Open-Meteo').all()
    assert len(raw) == raw.key.nunique()*168 and not raw.duplicated(['forecast_time','key']).any()
    stamp = raw.update_time.iloc[0]
    units, coordinates = load_city('beijing')
    assert set(raw.key) == set(coordinates)
    all_checks, differences = {}, {}
    for unit_id, weights in units.items():
        hourly = weighted_hourly(raw, weights, stamp)
        daily = calculate_daily_weather(hourly)
        frames = [(f'data/current/units/{unit_id}_hourly.csv',hourly),
                  (f'data/current/units/{unit_id}_daily.csv',daily)]
        if unit_id.endswith('_urban'):
            hi_hourly, hi_daily = heat_index_tables(hourly)
            frames += [(f'data/processed/units/{unit_id}_heat_index_hourly.csv',hi_hourly),
                       (f'data/processed/units/{unit_id}_heat_index_daily.csv',hi_daily)]
        else:
            risk = calculate_health_risk(daily)
            frames += [(f'data/processed/units/{unit_id}_health_risk.csv',risk)]
        for relative, expected in frames:
            # Compare against a serialize/read round-trip: representation is CSV, not Python type.
            serialized = io.StringIO()
            expected.to_csv(serialized,index=False)
            serialized.seek(0)
            all_checks[relative] = compare_frames(pd.read_csv(ROOT/relative),pd.read_csv(serialized),relative)
        if unit_id in ('beijing_110113','beijing_urban'):
            old_csv = subprocess.check_output(['git','-C',str(ROOT),'show',f'{args.before_ref}:data/static/units/{unit_id}_points.csv'])
            old = pd.read_csv(io.BytesIO(old_csv))
            old_weights = {key(row.latitude,row.longitude):row.area_weight for row in old.itertuples()}
            old_hourly = weighted_hourly(raw,old_weights,stamp)
            old_daily = calculate_daily_weather(old_hourly)
            vars_delta = {}
            for name, left, right in [('hourly',old_hourly,hourly),('daily',old_daily,daily)]:
                for column in right.select_dtypes(include='number').columns:
                    vars_delta[f'{name}.{column}'] = float(abs(right[column]-left[column]).max())
                for column in right.select_dtypes(exclude='number').columns:
                    vars_delta[f'{name}.{column}_changed_rows'] = int((right[column].astype(str)!=left[column].astype(str)).sum())
            if unit_id.endswith('_urban'):
                old_metrics=heat_index_tables(old_hourly)
                new_metrics=heat_index_tables(hourly)
            else:
                old_metrics=(calculate_health_risk(old_daily),)
                new_metrics=(calculate_health_risk(daily),)
            for i,(left,right) in enumerate(zip(old_metrics,new_metrics)):
                for column in right.select_dtypes(include='number').columns:
                    vars_delta[f'result_{i}.{column}']=float(abs(right[column]-left[column]).max())
                for column in right.columns:
                    if column not in right.select_dtypes(include='number').columns:
                        vars_delta[f'result_{i}.{column}_changed_rows']=int((right[column].astype(str)!=left[column].astype(str)).sum())
            differences[unit_id]=vars_delta
    legacy = [('data/current/beijing_center_forecast_hourly.csv','data/current/units/beijing_core_hourly.csv'),
              ('data/current/beijing_center_forecast_daily.csv','data/current/units/beijing_core_daily.csv'),
              ('data/processed/beijing_center_health_risk.csv','data/processed/units/beijing_core_health_risk.csv')]
    for path,unit_path in legacy:
        all_checks[path]=compare_frames(pd.read_csv(ROOT/path),pd.read_csv(ROOT/unit_path),path)
    changed = subprocess.check_output(['git','-C',str(ROOT),'diff','--name-only',args.before_ref,'--','data/current','data/processed'],text=True).splitlines()
    assert len(changed)==40
    assert all('/beijing_' in path for path in changed), 'Unrelated city outputs changed'
    snapshot=app.state.validate_snapshot()
    args.out.mkdir(parents=True,exist_ok=True)
    payload={'before_ref':args.before_ref,'update_time':stamp,'input_sha256':hashlib.sha256(args.input.read_bytes()).hexdigest(),
        'input_grid_points':raw.key.nunique(),'input_hours':168,'beijing_units':len(units),
        'recomputed_files':len(all_checks),'all_outputs_reproduce':True,'old_and_new_weights_same_input':differences,
        'changed_forecast_files':changed,'checks':all_checks,'whole_repository_snapshot':snapshot,
        'interpretation':'Weight comparison holds fetched raw weather fixed. New-vs-old published runs cannot be attributed solely to geometry; previous raw run was not retained.'}
    (args.out/'forecast_refresh_audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print('Verified all 40 Beijing files from saved input and full 45-unit API snapshot.')


if __name__ == '__main__':
    main()
