"""Fetch one city's unique IFS points and calculate its research units."""

import argparse
import csv
from datetime import datetime, timezone, timedelta
import math
import os
from pathlib import Path
import sys
import tempfile
import time

import pandas as pd
import requests

from calculate_health_risk import calculate_health_risk
from heat_index import heat_index_tables


ROOT = Path(__file__).resolve().parents[1]
POINTS_DIR = ROOT / "data/static/units"
API_URL = "https://api.open-meteo.com/v1/forecast"
BEIJING = timezone(timedelta(hours=8))
_window_start = time.monotonic()
_requested_points = 0


def key(lat, lon):
    return f"{float(lat):.10f},{float(lon):.10f}"


def coordinate_distance_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(float(lat1)), math.radians(float(lat2))
    dl, dn = b - a, math.radians(float(lon2) - float(lon1))
    h = math.sin(dl / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dn / 2) ** 2
    return 12_742_000 * math.asin(math.sqrt(h))


def load_city(city):
    manifest = pd.read_json(POINTS_DIR / "manifest.json")
    ids = manifest.loc[manifest.city.eq(city), "unit_id"].tolist()
    if not ids:
        raise ValueError(f"Unknown city: {city}")
    units, coordinates = {}, {}
    for unit_id in ids:
        with open(POINTS_DIR / f"{unit_id}_points.csv", encoding="utf-8-sig", newline="") as stream:
            points = list(csv.DictReader(stream))
        weights = {key(p["latitude"], p["longitude"]): float(p["area_weight"]) for p in points}
        if not points or len(weights) != len(points) or abs(sum(weights.values()) - 1) > 1e-6:
            raise ValueError(f"Bad weights: {unit_id}")
        units[unit_id] = weights
        for p in points:
            coordinates[key(p["latitude"], p["longitude"])] = (float(p["latitude"]), float(p["longitude"]))
    return units, coordinates


def fetch_city(coordinates, update_time):
    global _window_start, _requested_points
    rows, returned = [], set()
    items = list(coordinates.items())
    for start in range(0, len(items), 30):
        batch = items[start:start + 30]
        if _requested_points + len(batch) > 450:
            time.sleep(max(0, 61 - (time.monotonic() - _window_start)))
            _window_start, _requested_points = time.monotonic(), 0
        params = {
            "latitude": ",".join(str(pair[0]) for _, pair in batch),
            "longitude": ",".join(str(pair[1]) for _, pair in batch),
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "models": "ecmwf_ifs", "forecast_days": 7,
            "timezone": ",".join(["Asia/Shanghai"] * len(batch)),
            "wind_speed_unit": "ms", "cell_selection": "nearest",
            "elevation": ",".join(["nan"] * len(batch)),
        }
        for attempt in range(3):
            try:
                response = requests.get(API_URL, params=params, timeout=120)
            except requests.exceptions.RequestException:
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            if response.status_code != 429 or attempt == 2:
                break
            time.sleep(61)
            _window_start, _requested_points = time.monotonic(), 0
        response.raise_for_status()
        _requested_points += len(batch)
        data = response.json()
        locations = data if isinstance(data, list) else [data]
        if len(locations) != len(batch):
            raise ValueError("API location count differs from request")
        for (point_key, (lat, lon)), location in zip(batch, locations):
            actual = (location["latitude"], location["longitude"])
            if coordinate_distance_m(lat, lon, *actual) > 2:
                raise ValueError(f"IFS grid shifted: {point_key} -> {actual}")
            actual_key = key(*actual)
            if actual_key in returned:
                raise ValueError(f"Duplicate API grid: {actual}")
            returned.add(actual_key)
            hourly = location["hourly"]
            names = ("time", "temperature_2m", "relative_humidity_2m", "wind_speed_10m")
            values = [hourly[name] for name in names]
            if len({len(value) for value in values}) != 1 or len(values[0]) != 168:
                raise ValueError(f"Incomplete forecast: {point_key}")
            for forecast_time, temp, rh, wind in zip(*values):
                if any(v is None for v in (temp, rh, wind)) or not 0 <= rh <= 100 or wind < 0:
                    raise ValueError(f"Missing or invalid weather: {point_key} {forecast_time}")
                rows.append({"update_time": update_time, "forecast_time": forecast_time, "key": point_key,
                             "grid_latitude": lat, "grid_longitude": lon,
                             "api_return_latitude": actual[0], "api_return_longitude": actual[1],
                             "temperature_c": temp, "relative_humidity_pct": rh, "wind_speed_ms": wind,
                             "source": "Open-Meteo", "model": "ecmwf_ifs"})
        print(f"Fetched {min(start + 30, len(items))}/{len(items)} points", flush=True)
    raw = pd.DataFrame(rows)
    times = pd.DatetimeIndex(pd.to_datetime(raw.forecast_time.unique())).sort_values()
    if len(times) != 168 or not times.to_series().diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Forecast hours are not continuous")
    return raw


def weighted_hourly(raw, weights, update_time):
    subset = raw.loc[raw.key.isin(weights)].copy()
    expected = len(weights)
    if len(subset) != expected * 168 or subset.duplicated(["forecast_time", "key"]).any():
        raise ValueError("Missing or duplicate point-hours")
    subset["area_weight"] = subset.key.map(weights)
    if subset.area_weight.isna().any() or abs(sum(weights.values()) - 1) > 1e-6:
        raise ValueError("Invalid point weights")
    for src, dst in (("temperature_c", "temperature_c"),
                     ("relative_humidity_pct", "relative_humidity_pct"),
                     ("wind_speed_ms", "wind_speed_ms")):
        subset[dst] = subset[src] * subset.area_weight
    hourly = subset.groupby("forecast_time", as_index=False).agg(
        temperature_c=("temperature_c", "sum"),
        relative_humidity_pct=("relative_humidity_pct", "sum"),
        wind_speed_ms=("wind_speed_ms", "sum"),
        point_count=("key", "nunique"), weight_sum=("area_weight", "sum"))
    if len(hourly) != 168 or not hourly.point_count.eq(expected).all():
        raise ValueError("Incomplete weighted hours")
    hourly.insert(0, "update_time", update_time)
    hourly["source"] = "Open-Meteo"
    hourly["model"] = "ecmwf_ifs"
    return hourly


def daily_from_hourly(hourly):
    data = hourly.copy()
    data["forecast_time"] = pd.to_datetime(data.forecast_time)
    data["forecast_date"] = data.forecast_time.dt.date
    daily = data.groupby("forecast_date", as_index=False).agg(
        tmean_c=("temperature_c", "mean"), tmax_c=("temperature_c", "max"),
        rhmean_pct=("relative_humidity_pct", "mean"), vmean_ms=("wind_speed_ms", "mean"),
        hour_count=("forecast_time", "size"))
    daily["is_complete_day"] = daily.hour_count.eq(24)
    daily.insert(0, "update_time", hourly.update_time.iloc[0])
    daily["source"] = "Open-Meteo"
    daily["model"] = "ecmwf_ifs"
    return daily


def update_city(city):
    units, coordinates = load_city(city)
    update_time = datetime.now(BEIJING).isoformat(timespec="seconds")
    raw = fetch_city(coordinates, update_time)
    run_dir = ROOT / "data/raw/forecast_runs" / city
    run_dir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(run_dir / f"forecast_{datetime.now(BEIJING):%Y%m%d_%H%M%S}.csv", index=False)
    with tempfile.TemporaryDirectory(dir=ROOT / "data") as staging:
        pending = []
        for unit_id, weights in units.items():
            hourly = weighted_hourly(raw, weights, update_time)
            daily = daily_from_hourly(hourly)
            for directory, suffix, frame in (("current", "hourly", hourly),
                                              ("current", "daily", daily)):
                target = ROOT / "data" / directory / "units" / f"{unit_id}_{suffix}.csv"
                staged = Path(staging) / target.name
                frame.to_csv(staged, index=False, encoding="utf-8-sig")
                pending.append((staged, target))
            if unit_id.endswith("_urban"):
                hi_hourly, hi_daily = heat_index_tables(hourly)
                for suffix, frame in (("heat_index_hourly", hi_hourly), ("heat_index_daily", hi_daily)):
                    target = ROOT / "data/processed/units" / f"{unit_id}_{suffix}.csv"
                    staged = Path(staging) / target.name
                    frame.to_csv(staged, index=False, encoding="utf-8-sig")
                    pending.append((staged, target))
            else:
                risk = calculate_health_risk(daily)
                target = ROOT / "data/processed/units" / f"{unit_id}_health_risk.csv"
                staged = Path(staging) / target.name
                risk.to_csv(staged, index=False, encoding="utf-8-sig")
                pending.append((staged, target))
            print(f"Calculated {unit_id}", flush=True)
        for staged, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", choices=("beijing", "tianjin", "shijiazhuang", "tangshan", "handan", "baoding"))
    args = parser.parse_args()
    cities = [args.city] if args.city else ("beijing", "tianjin", "shijiazhuang", "tangshan", "handan", "baoding")
    failures = []
    for city in cities:
        try:
            update_city(city)
        except Exception as exc:
            failures.append(city)
            print(f"{city}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
