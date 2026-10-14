"""Local, guarded repair of the pinned Shunyi source and affected static artifacts.

Requires Shapely >=2.1, NumPy, SciPy, PyProj, pandas. Never reads/writes ERA5.
Run against an independent checkout of 0daab15; repeat runs use preserved before/.
"""
import argparse
import csv
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pyproj
import shapely
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=pathlib.Path, required=True)
parser.add_argument('--out', type=pathlib.Path, required=True)
args = parser.parse_args()
repo, out = args.repo.resolve(), args.out.resolve()
expected_commit = '0daab15d8813a4c52e88b708fd307b151e1d9b73'
expected_source_sha = 'a55de8f0fca8f2b4b43868e2e289fda34188ec7fb2925709325c5d7ed556ba3f'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip() == expected_commit, 'Use the pinned independent checkout'
sys.path.insert(0, str(repo / 'scripts'))
from build_spatial import build_units, calculate_points

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

affected = ['data/boundary_sources/110000.json',
            'data/static/units/beijing_110113.geojson', 'data/static/units/beijing_110113_points.csv',
            'data/static/units/beijing_urban.geojson', 'data/static/units/beijing_urban_points.csv',
            'data/static/units/manifest.json']
out.mkdir(parents=True, exist_ok=True)
for relative in affected:
    backup = out / 'before' / relative
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / relative, backup)
source = json.loads((out / 'before' / affected[0]).read_text(encoding='gb18030'))
assert digest(out / 'before' / affected[0]) == expected_source_sha, 'Original source backup must match pinned input'
feature = next(f for f in source['features'] if f['properties']['adcode'] == 110113)
original = shape(feature['geometry'])
assert original.geom_type == 'MultiPolygon' and len(original.geoms) == 2
assert not original.is_valid and all(p.is_valid for p in original.geoms)
assert original.geoms[0].intersection(original.geoms[1]).area == 0
reference = unary_union(original.geoms)
assert reference.is_valid and reference.geom_type == 'Polygon'
linework = shapely.make_valid(original)
structure = shapely.make_valid(original, method='structure', keep_collapsed=False)
polygonal = unary_union([g for g in linework.geoms if g.geom_type in ('Polygon','MultiPolygon')])
candidates = {'component_union': reference, 'buffer_zero': original.buffer(0),
              'make_valid_linework_polygon': polygonal, 'make_valid_structure': structure}
proj = Transformer.from_crs(4326, '+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m', always_xy=True).transform
ref_m = transform(proj, reference)
candidate_rows = {}
for name, candidate in candidates.items():
    projected = transform(proj, candidate)
    assert candidate.is_valid and candidate.equals(reference)
    row = {'valid': candidate.is_valid, 'geometry_type': candidate.geom_type,
           'components': 1 if candidate.geom_type == 'Polygon' else len(candidate.geoms),
           'holes': len(candidate.interiors) if candidate.geom_type == 'Polygon' else None,
           'area_km2': projected.area / 1e6,
           'symmetric_difference_reference_m2': projected.symmetric_difference(ref_m).area,
           'boundary_hausdorff_reference_m': projected.boundary.hausdorff_distance(ref_m.boundary),
           'lost_original_component_area_m2': [transform(proj,p).difference(projected).area for p in original.geoms]}
    candidate_rows[name] = row
    save(out / 'candidates' / f'{name}.geojson', {'type':'Feature','properties':{'method':name},'geometry':mapping(candidate)})
save(out / 'candidates/make_valid_full.geojson', {'type':'Feature','properties':{},'geometry':mapping(linework)})
save(out / 'candidates/shared_edges.geojson', {'type':'Feature','properties':{},'geometry':mapping(original.geoms[0].intersection(original.geoms[1]))})

# Merge the two valid adjacent faces; preserve the upstream MultiPolygon container.
feature['geometry'] = mapping(MultiPolygon([reference]))
fixed = json.loads(json.dumps(source))
before_data = json.loads((out / 'before' / affected[0]).read_text(encoding='gb18030'))
for old, new in zip(before_data['features'], fixed['features']):
    assert old['properties'] == new['properties']
    if old['properties']['adcode'] != 110113:
        assert old == new
source_path = repo / affected[0]
current = json.loads(source_path.read_text(encoding='gb18030'))
assert current in (before_data, fixed), 'Refuse to overwrite unrelated source edits'
source_path.write_text(json.dumps(source, ensure_ascii=False), encoding='gb18030')
units = build_units(repo / 'data/boundary_sources')
unchanged = {}
for unit_id, unit in units.items():
    if unit_id in ('beijing_110113', 'beijing_urban'):
        continue
    old = shape(json.loads((repo / f'data/static/units/{unit_id}.geojson').read_text(encoding='utf-8'))['geometry'])
    unchanged[unit_id] = old.equals(unit['geometry'])
assert all(unchanged.values())
weight_rows = {}
for unit_id in ('beijing_110113', 'beijing_urban'):
    unit = units[unit_id]
    points = calculate_points(unit['geometry'])
    target = repo / f'data/static/units/{unit_id}'
    target.with_suffix('.geojson').write_text(json.dumps({'type':'Feature','properties':{'unit_id':unit_id,'name':unit['name'],'district_codes':unit['codes']},'geometry':mapping(unit['geometry'])},ensure_ascii=False),encoding='utf-8')
    csv_path = target.with_name(target.name + '_points.csv')
    fields = ('point_id','latitude','longitude','intersect_area_km2','area_weight','grid_row_north')
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k:p[k] for k in fields} for p in points)
    old = pd.read_csv(out / 'before' / f'data/static/units/{unit_id}_points.csv')
    new = pd.DataFrame(points)
    old.index = list(zip(old.latitude.round(10), old.longitude.round(10)))
    new.index = list(zip(new.latitude.round(10), new.longitude.round(10)))
    keys = old.index.union(new.index)
    delta = new.area_weight.reindex(keys,fill_value=0) - old.area_weight.reindex(keys,fill_value=0)
    center = unit['geometry'].centroid
    laea = Transformer.from_crs(4326, f'+proj=laea +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m',always_xy=True).transform
    area = transform(laea, unit['geometry']).area/1e6
    covered = float(new.intersect_area_km2.sum())
    assert np.isfinite(new.area_weight).all() and (new.area_weight > 0).all()
    assert abs(new.area_weight.sum()-1) < 1e-12 and abs(covered-area) < .01
    old_geom = shape(json.loads((out/'before'/f'data/static/units/{unit_id}.geojson').read_text(encoding='utf-8'))['geometry'])
    weight_rows[unit_id] = {'old_geometry_valid':old_geom.is_valid,'new_geometry_valid':unit['geometry'].is_valid,
        'old_points':len(old),'new_points':len(new),'point_set_changes':len(set(old.index)^set(new.index)),
        'weight_sum':float(new.area_weight.sum()),'min_weight':float(new.area_weight.min()),
        'area_LAEA_km2':area,'covered_km2':covered,'coverage_error_km2':covered-area,
        'max_abs_old_stored_weight_change':float(abs(delta).max()),'weight_total_variation':float(abs(delta).sum()/2),
        'old_stored_area_sum_km2':float(old.intersect_area_km2.sum()),
        'symmetric_difference_old_valid_m2':transform(proj,old_geom).symmetric_difference(transform(proj,unit['geometry'])).area if old_geom.is_valid else None,
        'boundary_hausdorff_old_valid_m':transform(proj,old_geom).boundary.hausdorff_distance(transform(proj,unit['geometry']).boundary) if old_geom.is_valid else None}
    manifest_path = repo/'data/static/units/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entry = next(x for x in manifest if x['unit_id']==unit_id)
    entry['point_count'] = len(points)
    save(manifest_path, manifest)

for relative in affected:
    dest = out/'after'/relative
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(repo/relative,dest)
shared = original.geoms[0].intersection(original.geoms[1])
orig_m = transform(proj,original)
new_edges_outside_old = reference.boundary.difference(original.boundary)
assert new_edges_outside_old.is_empty
audit = {'commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
    'versions':{'python':sys.version,'shapely':shapely.__version__,'geos':shapely.geos_version_string,'pyproj':pyproj.__version__,'numpy':np.__version__,'pandas':pd.__version__},
    'original_reason':shapely.is_valid_reason(original),'original_components_valid':[p.is_valid for p in original.geoms],
    'original_component_areas_km2':[transform(proj,p).area/1e6 for p in original.geoms],
    'original_signed_area_sum_km2':orig_m.area/1e6,'original_overlap_m2':0,
    'selected_area_km2':ref_m.area/1e6,'area_delta_from_component_sum_m2':ref_m.area-sum(transform(proj,p).area for p in original.geoms),
    'original_boundary_set_densified_hausdorff_m':float(shapely.hausdorff_distance(orig_m.boundary,ref_m.boundary,densify=.001)),
    'retained_original_vertices_not_in_repair':len(set(tuple(c) for p in original.geoms for c in p.exterior.coords)-set(tuple(c) for ring in [reference.exterior,*reference.interiors] for c in ring.coords)),
    'shared_edges_length_m':transform(proj,shared).length,
    'shared_edges_outside_selected_boundary_m':transform(proj,shared).difference(ref_m.boundary).length,
    'new_boundary_edges_outside_original_boundary_length_m':transform(proj,new_edges_outside_old).length,
    'removed_edge_interpretation':'Internal duplicate shared seams removed; all new boundary edges are original edges. Densified all-ring Hausdorff is NOT an external-boundary position error.',
    'candidates':candidate_rows,'weights':weight_rows,'unchanged_units':unchanged,
    'files':[{'path':r,'before_sha256':digest(out/'before'/r),'after_sha256':digest(out/'after'/r)} for r in affected]}
save(out/'geometry_weights_audit.json',audit)
print(json.dumps(audit,ensure_ascii=False,indent=2))
