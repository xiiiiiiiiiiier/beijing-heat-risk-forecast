"""Run Beijing's forecast-to-health-risk calculation in one Python call."""

from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter

if __package__:
    from .calculate_center_average import save_hourly
    from .calculate_daily_weather import calculate_daily_weather, save_daily
    from .calculate_health_risk import RESULT_COLUMNS, calculate_health_risk, quality_control as check_health_risk, save_result
    from .update_units import BEIJING, fetch_city, load_city, weighted_hourly
else:
    from calculate_center_average import save_hourly
    from calculate_daily_weather import calculate_daily_weather, save_daily
    from calculate_health_risk import RESULT_COLUMNS, calculate_health_risk, quality_control as check_health_risk, save_result
    from update_units import BEIJING, fetch_city, load_city, weighted_hourly


ROOT = Path(__file__).resolve().parents[1]


def get_at_unit_ids(city):
    units, _ = load_city(city)
    return tuple(unit_id for unit_id in units if unit_id != f"{city}_urban")


def get_beijing_unit_ids():
    return get_at_unit_ids("beijing")


def get_tianjin_unit_ids():
    return get_at_unit_ids("tianjin")


def get_shijiazhuang_unit_ids():
    return get_at_unit_ids("shijiazhuang")


def save_unit_results(unit_id, hourly, daily, result):
    outputs = (
        (ROOT / "data/current/units" / f"{unit_id}_hourly.csv", hourly),
        (ROOT / "data/current/units" / f"{unit_id}_daily.csv", daily),
        (ROOT / "data/processed/units" / f"{unit_id}_health_risk.csv", result),
    )
    for path, frame in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False, encoding="utf-8-sig")


def run_city_forecast(city, unit_id, raw=None, save=True):
    units, coordinates = load_city(city)
    if unit_id not in units or unit_id == f"{city}_urban":
        raise ValueError(f"Unsupported {city.title()} unit_id: {unit_id}")
    weights = units[unit_id]
    update_time = (
        datetime.now(BEIJING).isoformat(timespec="seconds")
        if raw is None else raw["update_time"].iloc[0]
    )
    if raw is None:
        selected_coordinates = {point: coordinates[point] for point in weights}
        raw = fetch_city(selected_coordinates, update_time)

    hourly = weighted_hourly(raw, weights, update_time)
    daily = calculate_daily_weather(hourly)
    result = calculate_health_risk(daily)[RESULT_COLUMNS]
    check_health_risk(result)

    if save:
        save_unit_results(unit_id, hourly, daily, result)
        if city == "beijing" and unit_id == "beijing_core":
            save_hourly(hourly)
            save_daily(daily)
            save_result(result)
    return result


def run_beijing_forecast(unit_id="beijing_core", raw=None, save=True):
    """Return daily weather, AT, and age-group risks for one Beijing unit."""
    return run_city_forecast("beijing", unit_id, raw, save)


def run_tianjin_forecast(unit_id="tianjin_core", raw=None, save=True):
    """Return daily weather, AT, and age-group risks for one Tianjin unit."""
    return run_city_forecast("tianjin", unit_id, raw, save)


def run_shijiazhuang_forecast(unit_id="shijiazhuang_core", raw=None, save=True):
    """Return daily weather, AT, and age-group risks for one Shijiazhuang unit."""
    return run_city_forecast("shijiazhuang", unit_id, raw, save)


def main():
    start = perf_counter()
    try:
        result = run_beijing_forecast()
    except Exception as exc:
        print(f"北京计算链失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"北京计算链完成：{len(result)} 个自然日，耗时 {perf_counter() - start:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())
