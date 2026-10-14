import json
import pathlib
import sys
import argparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import shape
from shapely.ops import unary_union, transform
from shapely.affinity import translate, scale
from shapely.plotting import plot_polygon
from pyproj import Transformer

parser=argparse.ArgumentParser()
parser.add_argument('--out',type=pathlib.Path,required=True)
args=parser.parse_args()
out=args.out.resolve()
d=json.loads((out/'before/data/boundary_sources/110000.json').read_text(encoding='gb18030'))
g=shape(next(f for f in d['features'] if f['properties']['adcode']==110113)['geometry'])
r=unary_union(g.geoms)
proj=Transformer.from_crs(4326,'+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 +datum=WGS84 +units=m',always_xy=True).transform
origin=transform(proj,r).centroid
def local(geometry):
    return scale(translate(transform(proj,geometry),-origin.x,-origin.y),.001,.001,origin=(0,0))
plt.rcParams['font.family']='Microsoft YaHei'
plt.rcParams['axes.unicode_minus']=False
fig,axes=plt.subplots(1,2,figsize=(12,5),sharex=True,sharey=True)
for part,color in zip(g.geoms,['#c5dcec','#f1d0aa']):
    plot_polygon(local(part),ax=axes[0],add_points=False,color=color,edgecolor='#30465a',linewidth=1)
plot_polygon(local(r),ax=axes[1],add_points=False,color='#c5dcec',edgecolor='#30465a',linewidth=1)
for ax in axes:
    for line in local(g.geoms[0].intersection(g.geoms[1])).geoms:
        ax.plot(*line.xy,color='#c84535',linestyle='--',linewidth=2)
    ax.set_aspect('equal')
    ax.set_xlabel('相对等积投影坐标 / km')
    ax.grid(alpha=.2)
    ax.spines[['top','right']].set_visible(False)
axes[0].set_title('修复前：两个有效面，共享边导致 MultiPolygon 无效')
axes[1].set_title('修复后：一个面、保留原面域空洞')
axes[0].set_ylabel('相对等积投影坐标 / km')
fig.suptitle('顺义区拓扑修复：面域不变，合并共享边表达',fontsize=15)
fig.text(.5,.025,'红色虚线：原共享边，仅作问题定位；不是界线移动。此图不认证地图位置精度。',ha='center',fontsize=10)
fig.tight_layout(rect=[0,.10,1,.94])
fig.savefig(out/'顺义拓扑修复示意.png',dpi=180)
