"""NOAA Heat Index, with the effect categories published by ECMWF."""

import math

import pandas as pd


EFFECTS = (
    (51.1, "极端危险", "中暑的可能性很大"),
    (39.4, "危险", "可能出现中暑或热衰竭；长时间暴露或体力活动可能导致中暑"),
    (32.2, "极度谨慎", "长时间暴露或体力活动可能导致热痉挛、热衰竭或中暑"),
    (26.7, "注意", "长时间暴露或体力活动可能导致疲劳"),
)


def heat_index_c(temperature_c, humidity_pct):
    """Return HI in Celsius; NOAA's equations use Fahrenheit internally."""
    t, rh = float(temperature_c) * 1.8 + 32, float(humidity_pct)
    if not math.isfinite(t) or not math.isfinite(rh) or not 0 <= rh <= 100:
        raise ValueError("Invalid heat-index temperature or relative humidity")
    simple = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    hi = (simple + t) / 2
    if hi >= 80:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
              - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
    return (hi - 32) / 1.8


def classify(hi_c):
    for threshold, label, effect in EFFECTS:
        if hi_c >= threshold:
            return label, effect
    return "低于注意级别", "低于本表分级范围，不能据此认定没有热健康风险"


def heat_index_tables(hourly):
    required = ("update_time", "forecast_time", "temperature_c", "relative_humidity_pct", "source", "model")
    if hourly.empty or set(required) - set(hourly.columns):
        raise ValueError("Missing hourly heat-index inputs")
    data = hourly[list(required)].copy()
    data["forecast_time"] = pd.to_datetime(data.forecast_time)
    if data[list(required)].isna().any().any() or data.forecast_time.duplicated().any():
        raise ValueError("Missing or repeated heat-index input")
    data["hi_c"] = [heat_index_c(t, rh) for t, rh in zip(data.temperature_c, data.relative_humidity_pct)]
    classes = [classify(hi) for hi in data.hi_c]
    data["hi_class"] = [item[0] for item in classes]
    data["effect_on_body"] = [item[1] for item in classes]
    data["forecast_date"] = data.forecast_time.dt.date
    days = []
    for date, group in data.groupby("forecast_date", sort=True):
        peak = group.loc[group.hi_c.idxmax()]
        complete = len(group) == 24
        days.append({"update_time": peak.update_time, "forecast_date": date,
                     "hi_max_c": peak.hi_c, "hi_max_time": peak.forecast_time,
                     "hi_class": peak.hi_class if complete else "不完整日，不进入正式分级",
                     "effect_on_body": peak.effect_on_body if complete else "不完整日，不进入正式分级",
                     "hour_count": len(group), "is_complete_day": complete,
                     "source": peak.source, "model": peak.model})
    return data.drop(columns="forecast_date"), pd.DataFrame(days)
