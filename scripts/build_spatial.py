"""Build research units and O1280 nearest-centre area weights."""

import csv
import json
from pathlib import Path

import numpy as np
from numpy.polynomial.legendre import leggauss
from pyproj import CRS, Transformer
from scipy.spatial import Voronoi
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform, unary_union


ROOT = Path(__file__).resolve().parents[1]
CORE = {
    "beijing": ("110000", (110101, 110102, 110105, 110106, 110107, 110108)),
    "tianjin": ("120000", (120101, 120102, 120103, 120104, 120105, 120106)),
    "shijiazhuang": ("130100", (130102, 130104, 130105, 130108)),
    "tangshan": ("130200", (130202, 130203, 130205, 130207)),
    "handan": ("130400", (130403, 130402, 130404)),
    "baoding": ("130600", (130606, 130602)),
}
OTHER = {
    "beijing": (110109, 110111, 110112, 110113, 110114, 110115, 110116, 110117, 110118, 110119),
    "tianjin": (120110, 120111, 120112, 120113, 120114, 120115, 120116, 120117, 120118, 120119),
    "shijiazhuang": (130107, 130109, 130110, 130111),
    "tangshan": (130204, 130208, 130209),
    "handan": (130406, 130407, 130408),
    "baoding": (130607, 130608, 130609),
}


def build_units(source_dir):
    units = {}
    for city, (source, core_codes) in CORE.items():
        with open(Path(source_dir) / f"{source}.json", encoding="gb18030") as stream:
            features = json.load(stream)["features"]
        districts = {int(f["properties"]["adcode"]): f for f in features
                     if f["properties"].get("level") == "district"}
        missing = (set(core_codes) | set(OTHER[city])) - districts.keys()
        if missing:
            raise ValueError(f"{city}: missing core districts {sorted(missing)}")
        core_geometry = unary_union([shape(districts[c]["geometry"]) for c in core_codes])
        units[f"{city}_core"] = {"city": city, "name": "主城区", "codes": core_codes,
                                 "geometry": core_geometry}
        for code in (*core_codes, *OTHER[city]):
            feature = districts[code]
            units[f"{city}_{code}"] = {"city": city, "name": feature["properties"]["name"],
                                       "codes": (code,), "geometry": shape(feature["geometry"])}
    return units


def calculate_points(geometry):
    lon_min, lat_min, lon_max, lat_max = geometry.bounds
    lon0, lat0 = geometry.centroid.x, geometry.centroid.y
    crs = CRS.from_proj4(f"+proj=laea +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m")
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    area = transform(project, geometry)
    # Three or more surrounding grid rows keep every cell touching the study area finite.
    pad = 0.5
    roots = leggauss(2560)[0][::-1]
    centres = []
    for row, root in enumerate(roots[:1280], 1):
        lat = float(np.degrees(np.arcsin(root)))
        if not lat_min - pad <= lat <= lat_max + pad:
            continue
        count = 20 + 4 * (row - 1)
        for k in range(count):
            lon = 360 * k / count
            if lon_min - pad <= lon <= lon_max + pad:
                centres.append((lon, lat, row))
    xy = np.array([project(lon, lat) for lon, lat, _ in centres])
    voronoi = Voronoi(xy)
    points = []
    for i, (lon, lat, row) in enumerate(centres):
        region = voronoi.regions[voronoi.point_region[i]]
        if not region or -1 in region:
            continue
        polygon = Polygon(voronoi.vertices[region])
        intersect_area = polygon.intersection(area).area
        if intersect_area > 1:
            points.append({"latitude": lat, "longitude": lon,
                           "intersect_area_km2": intersect_area / 1_000_000,
                           "grid_row_north": row})
    points.sort(key=lambda p: (-p["latitude"], p["longitude"]))
    covered = sum(p["intersect_area_km2"] for p in points)
    if abs(covered - area.area / 1_000_000) > 0.01:
        raise ValueError(f"Voronoi area mismatch: {covered} vs {area.area / 1_000_000}")
    for index, point in enumerate(points, 1):
        point["point_id"] = f"P{index:03d}"
        point["area_weight"] = point["intersect_area_km2"] / covered
    return points


def main():
    target = ROOT / "data/static/units"
    target.mkdir(parents=True, exist_ok=True)
    units = build_units(ROOT / "data/boundary_sources")
    manifest = []
    for unit_id, unit in units.items():
        points = calculate_points(unit["geometry"])
        if unit_id == "beijing_core":
            # Keep the published Beijing weights exactly as the regression baseline.
            with open(ROOT / "data/static/forecast_points.csv", encoding="utf-8-sig", newline="") as stream:
                points = list(csv.DictReader(stream))
        with open(target / f"{unit_id}.geojson", "w", encoding="utf-8") as stream:
            json.dump({"type": "Feature", "properties": {"unit_id": unit_id, "name": unit["name"],
                       "district_codes": unit["codes"]}, "geometry": mapping(unit["geometry"])},
                      stream, ensure_ascii=False)
        with open(target / f"{unit_id}_points.csv", "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=("point_id", "latitude", "longitude",
                                                     "intersect_area_km2", "area_weight", "grid_row_north"))
            writer.writeheader()
            writer.writerows({name: point[name] for name in writer.fieldnames} for point in points)
        manifest.append({"unit_id": unit_id, "city": unit["city"], "name": unit["name"],
                         "district_codes": unit["codes"], "point_count": len(points)})
        print(unit_id, len(points))
    with open(target / "manifest.json", "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
