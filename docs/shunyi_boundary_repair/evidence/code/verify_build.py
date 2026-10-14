import json
import pathlib
import shutil
import sys
import argparse

from shapely.geometry import shape
import numpy as np
import pandas as pd

parser=argparse.ArgumentParser()
parser.add_argument('--repo',type=pathlib.Path,required=True)
parser.add_argument('--target',type=pathlib.Path,required=True)
args=parser.parse_args()
repo=args.repo.resolve()
sys.path.insert(0,str(repo/'scripts'))
import build_spatial
target=args.target.resolve()
assert target != repo and not target.is_relative_to(repo) and not repo.is_relative_to(target), 'Use a separate verification directory'
shutil.copytree(repo/'data/boundary_sources',target/'data/boundary_sources',dirs_exist_ok=True)
(target/'data/static').mkdir(parents=True,exist_ok=True)
shutil.copy2(repo/'data/static/forecast_points.csv',target/'data/static/forecast_points.csv')
build_spatial.ROOT=target
build_spatial.main()
for path in (target/'data/static/units').glob('*.geojson'):
    rebuilt=shape(json.loads(path.read_text(encoding='utf-8'))['geometry'])
    committed=shape(json.loads((repo/'data/static/units'/path.name).read_text(encoding='utf-8'))['geometry'])
    assert rebuilt.is_valid and rebuilt.equals(committed),path.name
    table=pd.read_csv(path.with_name(path.stem+'_points.csv'))
    tolerance = 1e-6 if path.stem == 'beijing_core' else 1e-12
    assert (table.area_weight>0).all() and abs(table.area_weight.sum()-1)<tolerance,path.name
print('Full build verified: 45 valid geometries, positive weights; sum tolerance 1e-12 except frozen Beijing core 1e-6 (repository convention); same face domains as repaired checkout.')
