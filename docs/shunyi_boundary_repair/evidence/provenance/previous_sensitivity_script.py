import sys, json, pathlib, hashlib
sys.path.insert(0, 'work/inspection_libs')
sys.path.insert(0, 'work/current_repo/scripts')
import h5py, numpy as np, pandas as pd
import shapely
from shapely.geometry import shape, box
from shapely.ops import transform
from shapely.affinity import translate
from pyproj import Transformer
from heat_index import heat_index_c, classify
from calculate_health_risk import calculate_at, classify_0_64, classify_65_plus

out = pathlib.Path('outputs/边界核查证据包')
data_path = pathlib.Path(r'C:\Users\11934\Desktop\qixiangshuju\era5_land_1991_06_jingjinji.nc')
with h5py.File(data_path) as f:
    arrays = []
    for name in ['t2m', 'd2m', 'u10', 'v10']:
        d = f[name]; a = d[:].astype(float)
        a[a == d.attrs['_FillValue']] = np.nan
        arrays.append(a.reshape(720, -1))
    lat, lon = f['latitude'][:], f['longitude'][:]
t, td, u, v = arrays
t -= 273.15; td -= 273.15
# Water-phase Magnus approximation; held fixed across scenarios, not a reference humidity validation.
rh = 100 * np.exp(17.625 * td / (243.04 + td) - 17.625 * t / (243.04 + t))
valid = np.logical_and.reduce([np.isfinite(x).all(axis=0) for x in [t, rh, u, v]])
humidity_qc = {'raw_max_pct':float(np.nanmax(rh)), 'above_100_count':int(np.count_nonzero(rh>100)), 'max_dewpoint_excess_C':float(np.nanmax(td-t))}
assert np.nanmin(rh) >= 0 and np.nanmax(rh) < 100.1, humidity_qc
# Bound only the recorded tiny saturation overshoot for this diagnostic sample.
rh = np.minimum(rh, 100)
wind = np.hypot(u, v)
proj = Transformer.from_crs(4326, '+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m', always_xy=True).transform
cells = np.array([transform(proj, box(float(x)-.05,float(y)-.05,float(x)+.05,float(y)+.05)) for y in lat for x in lon], dtype=object)
tree = shapely.STRtree(cells)

def weights(g):
    ix = tree.query(g, predicate='intersects')
    areas = shapely.area(shapely.intersection(cells[ix], g))
    use = (areas > 1) & valid[ix]
    w = np.zeros(len(cells)); w[ix[use]] = areas[use]
    assert w.sum() > 0
    w /= w.sum()
    assert abs(w.sum()-1) < 1e-12 and (w >= 0).all()
    return w

def metrics(w, urban):
    ix = w > 0
    tt, rr, vv = [a[:,ix] @ w[ix] for a in [t,rh,wind]]
    assert np.isfinite(tt).all() and np.isfinite(rr).all() and np.isfinite(vv).all()
    daily = [a[16:712].reshape(29,24).mean(axis=1) for a in [tt,rr,vv]]
    at = np.array([calculate_at(*vals)[1] for vals in zip(*daily)])
    hi = np.array([heat_index_c(x,y) for x,y in zip(tt,rr)])
    hi_daily = hi[16:712].reshape(29,24).max(axis=1)
    return tt, hi, at, hi_daily

rows, baseline, skipped = [], {}, []
for path in sorted(pathlib.Path('work/current_repo/data/static/units').glob('*.geojson')):
    g = shape(json.loads(path.read_text(encoding='utf-8'))['geometry'])
    if not g.is_valid:
        skipped.append({'unit':path.stem,'reason':'Invalid geometry; no authorized permanent geometry repair.'}); continue
    g = transform(proj, g); base = weights(g)
    b = metrics(base, path.stem.endswith('_urban')); baseline[path.stem] = {'points':int((base>0).sum())}
    assert np.allclose(weights(translate(g,0,0)),base,atol=1e-12)
    for distance in [100,500]:
        for direction, dx, dy in [('east',distance,0),('west',-distance,0),('north',0,distance),('south',0,-distance)]:
            w = weights(translate(g, dx, dy)); z = metrics(w, path.stem.endswith('_urban'))
            urban = path.stem.endswith('_urban')
            worst_hi = int(np.argmax(abs(z[1]-b[1])))
            def hi_input(weight, hour):
                idx=weight>0
                temp=float(t[hour,idx] @ weight[idx]); humid=float(rh[hour,idx] @ weight[idx])
                fahrenheit=temp*1.8+32
                selector=(0.5*(fahrenheit+61+(fahrenheit-68)*1.2+humid*.094)+fahrenheit)/2
                return {'T_C':temp,'RH_pct':humid,'branch_selector_F':selector,'HI_C':heat_index_c(temp,humid)}
            rows.append({'unit':path.stem,'distance_m':distance,'direction':direction,
                'baseline_points':int((base>0).sum()),'scenario_points':int((w>0).sum()),
                'point_set_changes':int(np.count_nonzero((base>0)!=(w>0))),
                'weight_total_variation':float(abs(w-base).sum()/2),
                'max_abs_T_hourly_C':float(abs(z[0]-b[0]).max()),
                'max_abs_HI_hourly_C':float(abs(z[1]-b[1]).max()) if urban else None,
                'worst_HI_hour_UTC_index':worst_hi if urban else None,
                'worst_HI_baseline_input':hi_input(base,worst_hi) if urban else None,
                'worst_HI_scenario_input':hi_input(w,worst_hi) if urban else None,
                'max_abs_AT_daily_C':float(abs(z[2]-b[2]).max()) if not urban else None,
                'HI_daily_class_changed_days':sum(classify(x)[0]!=classify(y)[0] for x,y in zip(z[3],b[3])) if urban else None,
                'AT_0_64_changed_days':sum(classify_0_64(x)!=classify_0_64(y) for x,y in zip(z[2],b[2])) if not urban else None,
                'AT_65_plus_changed_days':sum(classify_65_plus(x)!=classify_65_plus(y) for x,y in zip(z[2],b[2])) if not urban else None})
    print(path.stem, 'done', flush=True)
payload={'sample':'1991-06, 720 hours, 29 complete Beijing days',
    'data_sha256':hashlib.sha256(data_path.read_bytes()).hexdigest(),
    'grid':'ERA5-Land regular 0.1 degree cell-area intersections; NOT IFS O1280 weights',
    'scenarios':'100/500 m translations east/west/north/south in equal-area projection; hypothetical stress tests, not measured coordinate error',
    'support':'Same month-fixed jointly valid input grid support for all scenarios; weights normalized over available support. No coastline/water or historical-boundary assessment.',
    'humidity':'100*exp(17.625*Td/(243.04+Td)-17.625*T/(243.04+T)); Celsius; fixed approximation across scenarios',
    'humidity_qc':humidity_qc,'skipped':skipped,'rows':rows}
(out/'结果敏感性明细.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
print('scenarios',len(rows),'skipped',skipped)
for field in ['max_abs_T_hourly_C','max_abs_HI_hourly_C','max_abs_AT_daily_C']:
    for d in [100,500]:
        candidates=[r for r in rows if r['distance_m']==d and r[field] is not None]
        r=max(candidates,key=lambda r:r[field]);print(field,d,r['unit'],r[field])
print('classification changes',{f:sum(r[f] or 0 for r in rows) for f in ['HI_daily_class_changed_days','AT_0_64_changed_days','AT_65_plus_changed_days']})
