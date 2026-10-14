"""ERA5-Land diagnostics: previous audit's 0.1-degree support and formulas.

All files written below --out; sample is opened read-only. HI for Shunyi is
diagnostic only. Never substitutes ERA5 weights for repository IFS weights.
"""
import argparse
import hashlib
import json
import pathlib
import sys
from datetime import timezone, timedelta

import h5py
import numpy as np
import pandas as pd
import shapely
from shapely.affinity import translate
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=pathlib.Path, required=True)
parser.add_argument('--out', type=pathlib.Path, required=True)
parser.add_argument('--sample', type=pathlib.Path, required=True)
parser.add_argument('--previous-results', type=pathlib.Path)
args = parser.parse_args()
repo, out, sample = args.repo.resolve(), args.out.resolve(), args.sample.resolve()
sys.path.insert(0, str(repo/'scripts'))
from heat_index import heat_index_c, classify
from calculate_health_risk import calculate_at, classify_0_64, classify_65_plus

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def save(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

initial_sha = sha(sample)
initial_stat = sample.stat()
with h5py.File(sample,'r') as f:
    assert f['valid_time'].attrs['units'].decode() == 'seconds since 1970-01-01'
    times = pd.to_datetime(f['valid_time'][:],unit='s',utc=True)
    assert len(times)==720 and times[0]==pd.Timestamp('1991-06-01',tz='UTC')
    assert (times[1:]-times[:-1] == pd.Timedelta(hours=1)).all()
    lat,lon = f['latitude'][:],f['longitude'][:]
    assert np.allclose(abs(np.diff(lat)),.1,atol=1e-5) and np.allclose(np.diff(lon),.1,atol=1e-5)
    arrays = []
    for name in ['t2m','d2m','u10','v10']:
        dataset = f[name]
        a = dataset[:].astype(float)
        a[a == dataset.attrs['_FillValue']] = np.nan
        assert a.shape == (720,len(lat),len(lon))
        arrays.append(a.reshape(720,-1))
t,td,u,v = arrays
t -= 273.15
td -= 273.15
rh = 100*np.exp(17.625*td/(243.04+td)-17.625*t/(243.04+t))
valid = np.logical_and.reduce([np.isfinite(x).all(axis=0) for x in [t,rh,u,v]])
humidity_qc = {'raw_max_pct':float(np.nanmax(rh)), 'above_100_count':int(np.count_nonzero(rh>100)), 'max_dewpoint_excess_C':float(np.nanmax(td-t))}
assert np.nanmin(rh)>=0 and np.nanmax(rh)<100.1
rh = np.minimum(rh,100)
wind = np.hypot(u,v)
proj = Transformer.from_crs(4326,'+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m',always_xy=True).transform
cells = np.array([transform(proj,box(float(x)-.05,float(y)-.05,float(x)+.05,float(y)+.05)) for y in lat for x in lon],dtype=object)
tree = shapely.STRtree(cells)
# Preserve previous audit's fixed UTC+8 day grouping, including its historical DST limit.
beijing_times = times.tz_convert(timezone(timedelta(hours=8)))
assert beijing_times[16].hour==0 and beijing_times[711].hour==23
assert len(set(beijing_times[16:712].date))==29

def weights(g, label):
    ix = tree.query(g,predicate='intersects')
    areas = shapely.area(shapely.intersection(cells[ix],g))
    use = (areas>1)&valid[ix]
    w = np.zeros(len(cells))
    w[ix[use]]=areas[use]
    covered = float(w.sum())
    assert covered>0
    w/=covered
    assert (w>=0).all() and abs(w.sum()-1)<1e-12
    footprint = float(areas.sum())
    assert abs(footprint-g.area)<1
    # This sample has full valid support for all selected study geometries.
    assert abs(covered-g.area)<1
    ids = np.flatnonzero(w)
    folder = out/'era5_weights'
    folder.mkdir(parents=True,exist_ok=True)
    pd.DataFrame({'flat_grid_index':ids,'latitude':lat[ids//len(lon)],'longitude':lon[ids%len(lon)],
        'intersection_area_m2':w[ids]*covered,'area_weight':w[ids]}).to_csv(folder/f'{label}.csv',index=False,encoding='utf-8-sig')
    return w, {'points':len(ids),'weight_sum':float(w.sum()),'min_positive_weight':float(w[ids].min()),
        'geometry_area_km2':g.area/1e6,'all_grid_coverage_km2':footprint/1e6,'valid_support_area_km2':covered/1e6,
        'valid_support_coverage_fraction':covered/g.area,'coverage_error_m2':covered-g.area}

def metrics(w,label):
    ix = w>0
    tt,rr,vv = [a[:,ix]@w[ix] for a in [t,rh,wind]]
    hi = np.array([heat_index_c(x,y) for x,y in zip(tt,rr)])
    daily = [a[16:712].reshape(29,24).mean(axis=1) for a in [tt,rr,vv]]
    at = np.array([calculate_at(*vals)[1] for vals in zip(*daily)])
    hi_daily = hi[16:712].reshape(29,24).max(axis=1)
    assert np.isfinite(np.concatenate([tt,rr,vv,hi,at])).all()
    folder=out/'era5_metrics'
    folder.mkdir(parents=True,exist_ok=True)
    pd.DataFrame({'time_UTC':times.astype(str),'time_Beijing':beijing_times.astype(str),
        'T_C':tt,'RH_pct':rr,'wind_ms':vv,'HI_diagnostic_C':hi}).to_csv(folder/f'{label}_hourly.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame({'date_Beijing':beijing_times[16:712:24].date,'T_mean_C':daily[0],
        'RH_mean_pct':daily[1],'wind_mean_ms':daily[2],'AT_C':at,
        'AT_0_64_class':[classify_0_64(x) for x in at],'AT_65_plus_class':[classify_65_plus(x) for x in at],
        'HI_max_diagnostic_C':hi_daily,'HI_class_diagnostic':[classify(x)[0] for x in hi_daily]}).to_csv(folder/f'{label}_daily.csv',index=False,encoding='utf-8-sig')
    return tt,hi,at,hi_daily,rr

def compare(base, result):
    return {'max_abs_T_hourly_C':float(abs(result[0]-base[0]).max()),
        'max_abs_HI_hourly_C':float(abs(result[1]-base[1]).max()),
        'max_abs_AT_daily_C':float(abs(result[2]-base[2]).max()),
        'HI_daily_class_changed_days':sum(classify(x)[0]!=classify(y)[0] for x,y in zip(result[3],base[3])),
        'AT_0_64_changed_days':sum(classify_0_64(x)!=classify_0_64(y) for x,y in zip(result[2],base[2])),
        'AT_65_plus_changed_days':sum(classify_65_plus(x)!=classify_65_plus(y) for x,y in zip(result[2],base[2]))}

g = shape(json.loads((repo/'data/static/units/beijing_110113.geojson').read_text(encoding='utf-8'))['geometry'])
assert g.is_valid
g = transform(proj,g)
base,base_info = weights(g,'shunyi_repaired')
b = metrics(base,'shunyi_repaired')
assert np.allclose(weights(translate(g,0,0),'shunyi_zero_shift')[0],base,atol=1e-12,rtol=0)
rows=[]
for distance in [100,500]:
    for direction,dx,dy in [('east',distance,0),('west',-distance,0),('north',0,distance),('south',0,-distance)]:
        label=f'shunyi_{distance}m_{direction}'
        w,info=weights(translate(g,dx,dy),label)
        z=metrics(w,label)
        row={'unit':'beijing_110113','distance_m':distance,'direction':direction,
            'point_set_changes':int(np.count_nonzero((w>0)!=(base>0))),
            'weight_total_variation':float(abs(w-base).sum()/2),'weight_check':info,**compare(b,z)}
        worst=int(np.argmax(abs(z[1]-b[1])))
        def inputs(result):
            temp,hum=result[0][worst],result[4][worst]
            fahrenheit=temp*1.8+32
            selector=(.5*(fahrenheit+61+(fahrenheit-68)*1.2+hum*.094)+fahrenheit)/2
            return {'T_C':float(temp),'RH_pct':float(hum),'branch_selector_F':float(selector),'HI_C':float(result[1][worst])}
        row.update({'worst_HI_time_UTC':str(times[worst]),'worst_HI_baseline_input':inputs(b),'worst_HI_scenario_input':inputs(z)})
        rows.append(row)
candidate_comparisons={}
for path in sorted((out/'candidates').glob('*.geojson')):
    if path.stem in ('make_valid_full','shared_edges'):
        continue
    cg=transform(proj,shape(json.loads(path.read_text(encoding='utf-8'))['geometry']))
    cw,info=weights(cg,path.stem)
    cm=metrics(cw,path.stem)
    candidate_comparisons[path.stem]={'weight_max_abs_difference':float(abs(cw-base).max()),**compare(b,cm)}
    assert abs(cw-base).max()<1e-12 and candidate_comparisons[path.stem]['max_abs_T_hourly_C']<1e-10
old_source=json.loads((out/'before/data/boundary_sources/110000.json').read_text(encoding='gb18030'))
old_g=shape(next(f for f in old_source['features'] if f['properties']['adcode']==110113)['geometry'])
# Both components are valid and disjoint in area, so summing their cell intersections
# supplies an independent component-based baseline without intersecting invalid MultiPolygon.
component_area=np.zeros(len(cells))
for piece in old_g.geoms:
    piece=transform(proj,piece)
    ix=tree.query(piece,predicate='intersects')
    component_area[ix]+=shapely.area(shapely.intersection(cells[ix],piece))
component_area[(component_area<=1)|(~valid)]=0
component_weights=component_area/component_area.sum()
component_metric=metrics(component_weights,'shunyi_original_valid_components')
component_comparison={'baseline_kind':'sum of independent original valid Polygon cell intersections; NOT original invalid MultiPolygon overlay',
    'weight_max_abs_difference':float(abs(component_weights-base).max()),**compare(b,component_metric)}
assert component_comparison['weight_max_abs_difference']<1e-12
urban=[]
for version in ['before','after']:
    ug=shape(json.loads((out/version/'data/static/units/beijing_urban.geojson').read_text(encoding='utf-8'))['geometry'])
    assert ug.is_valid
    uw,ui=weights(transform(proj,ug),'beijing_urban_'+version)
    urban.append((uw,metrics(uw,'beijing_urban_'+version),ui))
urban_comparison={'weight_max_abs_difference':float(abs(urban[0][0]-urban[1][0]).max()),
    'before_weight_check':urban[0][2],'after_weight_check':urban[1][2],**compare(urban[0][1],urban[1][1])}
assert urban_comparison['weight_max_abs_difference']<1e-12
previous_check = None
if args.previous_results:
    previous = json.loads(args.previous_results.read_text(encoding='utf-8'))
    assert previous['data_sha256']==initial_sha
    previous_row = next(r for r in previous['rows'] if r['unit']=='beijing_urban' and r['distance_m']==100 and r['direction']=='east')
    shifted, _ = weights(translate(transform(proj,ug),100,0),'beijing_urban_prior_method_check')
    result = compare(urban[1][1],metrics(shifted,'beijing_urban_prior_method_check'))
    fields = ['max_abs_T_hourly_C','max_abs_HI_hourly_C','HI_daily_class_changed_days']
    previous_check = {field:{'previous':previous_row[field],'reproduced':result[field]} for field in fields}
    assert all(abs(previous_row[field]-result[field])<1e-9 for field in fields)
assert sha(sample)==initial_sha and sample.stat().st_mtime_ns==initial_stat.st_mtime_ns
payload={'sample':str(sample),'sample_sha256_before_and_after':initial_sha,'ERA5_unmodified':True,
    'period':'720 UTC hours 1991-06-01 through 1991-06-30; 29 complete Beijing days 1991-06-02 through 1991-06-30',
    'day_grouping':'fixed UTC+8, same as previous audit; not historical Asia/Shanghai daylight saving time',
    'grid':'ERA5-Land regular 0.1 degree cell-area intersection; NOT IFS O1280',
    'projection':'Albers equal area lat_1=25 lat_2=47 lat_0=0 lon_0=105 datum=WGS84',
    'humidity':'same previous audit water-phase Magnus; RH tiny excess clipped to 100% only for diagnostics',
    'humidity_qc':humidity_qc,'support':'month-fixed jointly finite T/RH/u/v grids; normalization over same available support',
    'formal_status':'Repository Shunyi: T/weather and daily AT+age classes; HI is only diagnostic here. All ERA5 files are diagnostic, not live forecast outputs.',
    'baseline_limit':'No trusted direct invalid-MultiPolygon overlay baseline. Valid original components have zero area overlap and supply an independently evaluated face-area baseline.',
    'baseline_weight_check':base_info,'original_component_baseline_comparison':component_comparison,
    'candidate_comparisons':candidate_comparisons,'beijing_urban_comparison':urban_comparison,
    'previous_audit_method_reproduction':previous_check,'rows':rows}
save(out/'sensitivity_results.json',payload)
print(json.dumps({'baseline':base_info,'component_comparison':component_comparison,'urban_comparison':urban_comparison,'rows':rows},ensure_ascii=False,indent=2))
