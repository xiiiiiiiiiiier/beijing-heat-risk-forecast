"""Aggregate the center's hourly forecast by Beijing calendar day."""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
HOURLY = ROOT / "data/current/beijing_center_forecast_hourly.csv"
DAILY = ROOT / "data/current/beijing_center_forecast_daily.csv"
REQUIRED = (
    "update_time", "forecast_time", "temperature_c", "relative_humidity_pct",
    "wind_speed_ms", "source", "model",
)
NUMERIC = ("temperature_c", "relative_humidity_pct", "wind_speed_ms")


def calculate_daily_weather(hourly):
    hourly = hourly.copy()
    missing = set(REQUIRED) - set(hourly.columns)
    if missing:
        raise ValueError(f"hourly 缺少字段：{', '.join(sorted(missing))}")
    if hourly.empty or hourly[list(REQUIRED)].isna().any().any():
        raise ValueError("hourly 为空或必需字段有缺失")

    # Upstream writes naive Beijing local times; explicit offsets are converted to Beijing.
    def beijing_time(value):
        time = pd.Timestamp(value)
        return time.tz_localize("Asia/Shanghai") if time.tzinfo is None else time.tz_convert("Asia/Shanghai")

    try:
        hourly["forecast_time"] = pd.DatetimeIndex(hourly["forecast_time"].map(beijing_time))
        for column in NUMERIC:
            hourly[column] = pd.to_numeric(hourly[column], errors="raise")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"hourly 时间或气象数值无效：{exc}") from exc
    if hourly["forecast_time"].isna().any() or hourly[list(NUMERIC)].isna().any().any():
        raise ValueError("hourly 时间或气象数值有缺失")
    if not hourly["relative_humidity_pct"].between(0, 100).all() or (hourly["wind_speed_ms"] < 0).any():
        raise ValueError("hourly 相对湿度须为 0–100%，风速须非负")
    for column in ("update_time", "source", "model"):
        if hourly[column].nunique() != 1 or hourly[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"hourly 的 {column} 必须为同一非空值")

    hourly = hourly.sort_values("forecast_time")
    duplicates = int(hourly["forecast_time"].duplicated().sum())
    if duplicates:
        raise ValueError(f"hourly 存在 {duplicates} 个重复 forecast_time")
    if not hourly["forecast_time"].diff().dropna().eq(pd.Timedelta(hours=1)).all():
        raise ValueError("hourly 时间存在缺失或间隔不是 1 小时")

    hourly["forecast_date"] = hourly["forecast_time"].dt.date
    daily = hourly.groupby("forecast_date", as_index=False).agg(
        tmean_c=("temperature_c", "mean"),
        tmax_c=("temperature_c", "max"),
        rhmean_pct=("relative_humidity_pct", "mean"),
        vmean_ms=("wind_speed_ms", "mean"),
        hour_count=("forecast_time", "size"),
    )
    daily["is_complete_day"] = daily["hour_count"].eq(24)
    daily.insert(0, "update_time", hourly["update_time"].iloc[0])
    daily["source"] = hourly["source"].iloc[0]
    daily["model"] = hourly["model"].iloc[0]
    if daily.isna().any().any() or (daily["tmax_c"] < daily["tmean_c"]).any():
        raise ValueError("daily 关键字段缺失或 Tmax < Tmean")
    if not daily["rhmean_pct"].between(0, 100).all() or (daily["vmean_ms"] < 0).any():
        raise ValueError("daily 相对湿度或风速越界")

    complete = int(daily["is_complete_day"].sum())
    print(f"hourly 行数：{len(hourly)}；重复时间：{duplicates}")
    print(f"自然日：{len(daily)}；完整：{complete}；不完整：{len(daily) - complete}")
    return daily


def save_daily(daily):
    DAILY.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(DAILY, index=False, encoding="utf-8-sig")
    print(f"输出：{DAILY}")


def main():
    if not HOURLY.is_file():
        raise FileNotFoundError(f"未找到 hourly 文件：{HOURLY}")
    save_daily(calculate_daily_weather(pd.read_csv(HOURLY)))


if __name__ == "__main__":
    main()
