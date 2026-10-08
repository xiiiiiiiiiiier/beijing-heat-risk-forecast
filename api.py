"""Read-only HTTP access to the first-stage forecast outputs; no recalculation."""

import csv
import json
import logging
import os
from contextlib import asynccontextmanager
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Generic, TypeVar

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parent
BEIJING = timezone(timedelta(hours=8))
CITY_NAMES = dict(zip(
    ("beijing", "tianjin", "shijiazhuang", "tangshan", "handan", "baoding"),
    ("北京", "天津", "石家庄", "唐山", "邯郸", "保定"),
))
logger = logging.getLogger(__name__)


def local_time(value):
    value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return (value.replace(tzinfo=BEIJING) if value.tzinfo is None else value.astimezone(BEIJING))


LocalTime = Annotated[datetime, BeforeValidator(local_time)]
OptionalNumber = Annotated[float | None, BeforeValidator(lambda v: None if v == "" else v)]


class Row(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_min_length=1)
    update_time: LocalTime
    source: str
    model: str


class Hourly(Row):
    forecast_time: LocalTime
    temperature_c: float
    relative_humidity_pct: float = Field(ge=0, le=100)
    wind_speed_ms: float = Field(ge=0)
    point_count: int = Field(gt=0)
    weight_sum: float = Field(ge=0.999999, le=1.000001)


class Day(Row):
    forecast_date: date
    hour_count: int = Field(ge=1, le=24)
    is_complete_day: bool

    @model_validator(mode="after")
    def complete_day_matches_count(self):
        if self.is_complete_day != (self.hour_count == 24):
            raise ValueError("Day completeness contradicts hour_count")
        return self


class Daily(Day):
    tmean_c: float
    tmax_c: float
    rhmean_pct: float = Field(ge=0, le=100)
    vmean_ms: float = Field(ge=0)


class HealthRisk(Daily):
    vapor_pressure_hpa: OptionalNumber
    at_c: OptionalNumber
    risk_0_64: str
    risk_65_plus: str

    @model_validator(mode="after")
    def complete_day_has_results(self):
        if self.is_complete_day and (self.at_c is None or self.vapor_pressure_hpa is None):
            raise ValueError("Complete day has missing AT results")
        return self


class HIHourly(Row):
    forecast_time: LocalTime
    temperature_c: float
    relative_humidity_pct: float = Field(ge=0, le=100)
    hi_c: float
    hi_class: str
    effect_on_body: str


class HIDaily(Day):
    hi_max_c: float
    hi_max_time: LocalTime
    hi_class: str
    effect_on_body: str


class Unit(BaseModel):
    unit_id: str = Field(pattern=r"^[a-z]+_(core|urban|[0-9]{6})$")
    city: str
    name: str
    district_codes: list[int]
    point_count: int = Field(gt=0)
    indicators: list[str]


T = TypeVar("T", bound=Row)


class Forecast(BaseModel, Generic[T]):
    unit: Unit
    timezone: str = "Asia/Shanghai"
    data_kind: str = "forecast"
    update_time: datetime
    data_age_hours: float
    is_stale: bool
    rows: list[T]
    snapshot_revision: str | None = None


class City(BaseModel):
    city: str
    name: str
    unit_count: int


class CityStatus(BaseModel):
    city: str
    update_time: datetime
    is_stale: bool


class SnapshotStatus(BaseModel):
    snapshot_revision: str | None
    unit_count: int
    file_count: int
    cities: list[CityStatus]


def create_app(data_dir: Path = ROOT / "data") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("VALIDATE_SNAPSHOT_ON_START") == "1":
            validate_snapshot()
        yield

    app = FastAPI(title="京津冀六市高温健康风险预报 API", version="0.1.0",
                  lifespan=lifespan,
                  description="读取第一链 CSV。AT 与 HI 按现有空间范围提供，数据超过 24 小时标为陈旧。")
    data_dir = Path(data_dir)
    revision = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GITHUB_SHA")
    origins = [s.strip() for s in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if s.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_credentials=False)

    def units():
        try:
            manifest = json.loads((data_dir / "static/units/manifest.json").read_text(encoding="utf-8-sig"))
            if not isinstance(manifest, list) or any(
                not isinstance(u, dict) or not isinstance(u.get("unit_id"), str) for u in manifest
            ):
                raise ValueError("Invalid manifest shape")
            items = [Unit.model_validate({**u, "indicators": ["hi" if u["unit_id"].endswith("_urban") else "at"]})
                     for u in manifest]
            if not items or len({u.unit_id for u in items}) != len(items):
                raise ValueError("Empty or duplicate units")
            if any(u.city not in CITY_NAMES or not u.unit_id.startswith(u.city + "_") for u in items):
                raise ValueError("Invalid city/unit mapping")
            return {u.unit_id: u for u in items}
        except (OSError, ValueError, TypeError, KeyError):
            logger.exception("Cannot read unit manifest")
            raise HTTPException(503, "空间单元清单不可用") from None

    def read(unit_id, directory, suffix, row_type, indicator=None):
        unit = units().get(unit_id)
        if unit is None:
            raise HTTPException(404, "未知空间单元")
        if indicator and indicator not in unit.indicators:
            raise HTTPException(422, "此空间单元不支持请求的指标，请查看 indicators")
        try:
            with (data_dir / directory / "units" / f"{unit_id}_{suffix}.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = [row_type.model_validate(row) for row in csv.DictReader(stream)]
            if not rows or len({r.update_time for r in rows}) != 1:
                raise ValueError("Empty or mixed forecast runs")
            if len({(r.source, r.model) for r in rows}) != 1:
                raise ValueError("Mixed data sources")
            key = "forecast_time" if suffix.endswith("hourly") else "forecast_date"
            times = [getattr(r, key) for r in rows]
            if times != sorted(set(times)):
                raise ValueError("Repeated or unordered forecast times")
            if key == "forecast_time":
                if len(times) != 168 or any(b - a != timedelta(hours=1) for a, b in zip(times, times[1:])):
                    raise ValueError("Expected 168 continuous forecast hours")
                if row_type is Hourly and any(r.point_count != unit.point_count for r in rows):
                    raise ValueError("Point count does not match unit manifest")
        except (OSError, ValueError, TypeError, csv.Error):
            logger.exception("Cannot serve forecast %s/%s", unit_id, suffix)
            raise HTTPException(503, "预报数据缺失或格式不正确，请等待数据更新") from None
        age = max(0, (datetime.now(BEIJING) - rows[0].update_time).total_seconds() / 3600)
        return dict(unit=unit, update_time=rows[0].update_time, data_age_hours=round(age, 2),
                    is_stale=age > 24, rows=rows, snapshot_revision=revision)

    def validate_snapshot():
        """Check one committed dataset before publishing or starting a deployment."""
        items = units()
        expected = dict(beijing=12, tianjin=12, shijiazhuang=6, tangshan=5, handan=5, baoding=5)
        if Counter(u.city for u in items.values()) != expected:
            raise HTTPException(503, "六市空间单元数量不完整")
        city_runs = {}
        file_count = 0
        for uid, unit in items.items():
            hourly = read(uid, "current", "hourly", Hourly)
            daily = read(uid, "current", "daily", Daily)
            tables = [hourly, daily]
            if unit.indicators == ["at"]:
                result = read(uid, "processed", "health_risk", HealthRisk, "at")
                tables.append(result)
                if [r.model_dump(include=set(Daily.model_fields)) for r in result['rows']] != [r.model_dump() for r in daily['rows']]:
                    raise HTTPException(503, f"{uid} 的风险与日气象不匹配")
            else:
                tables.extend([read(uid, "processed", "heat_index_hourly", HIHourly, "hi"),
                               read(uid, "processed", "heat_index_daily", HIDaily, "hi")])
                for weather, hi in zip(hourly['rows'], tables[2]['rows']):
                    if any(getattr(weather, k) != getattr(hi, k) for k in
                           ('forecast_time', 'temperature_c', 'relative_humidity_pct')):
                        raise HTTPException(503, f"{uid} 的 HI 与小时气象不匹配")
            run = hourly['update_time']
            if city_runs.setdefault(unit.city, run) != run:
                raise HTTPException(503, f"{unit.city} 存在混合更新批次")
            counts = Counter(r.forecast_time.date() for r in hourly['rows'])
            for table in tables:
                file_count += 1
                if table['update_time'] != run:
                    raise HTTPException(503, f"{uid} 存在混合更新批次")
                if {(r.source, r.model) for r in table['rows']} != {(hourly['rows'][0].source, hourly['rows'][0].model)}:
                    raise HTTPException(503, f"{uid} 存在混合数据源")
                if isinstance(table['rows'][0], Day):
                    if {r.forecast_date: r.hour_count for r in table['rows']} != dict(counts):
                        raise HTTPException(503, f"{uid} 的日结果与小时结果不匹配")
        if max(city_runs.values()) - min(city_runs.values()) > timedelta(hours=2):
            raise HTTPException(503, "六市更新时间跨度超过两小时，疑似混合更新轮次")
        return {"snapshot_revision": revision, "unit_count": len(items), "file_count": file_count,
                "cities": [{"city": city, "update_time": stamp,
                            "is_stale": datetime.now(BEIJING) - stamp > timedelta(hours=24)}
                           for city, stamp in city_runs.items()]}

    app.state.validate_snapshot = validate_snapshot

    @app.get("/api/v1/status", response_model=SnapshotStatus)
    def data_status():
        """校验六市整批数据并返回各市更新时间。陈旧数据仍保留，显示 is_stale。"""
        return validate_snapshot()

    @app.get("/health")
    def health():
        """进程存活检查，不代表计算、数据新鲜度或 GitHub 部署正常。"""
        return {"status": "ok"}

    @app.get("/api/v1/cities", response_model=list[City])
    def cities():
        available = units().values()
        return [{"city": city, "name": name, "unit_count": sum(u.city == city for u in available)}
                for city, name in CITY_NAMES.items()]

    @app.get("/api/v1/cities/{city}/units", response_model=list[Unit])
    def city_units(city: str):
        if city not in CITY_NAMES:
            raise HTTPException(404, "未知城市")
        return [u for u in units().values() if u.city == city]

    @app.get(
        "/api/v1/cities/{city}/risk",
        status_code=501,
        summary="城市综合健康风险（预留，尚未实现）",
        description="城市综合健康风险的科研方法和结果尚未完成。现有 AT 年龄组风险与全市市辖区合并区域 HI 不是城市综合风险。",
        responses={404: {"description": "未知城市"}, 501: {"description": "城市综合健康风险尚未实现"}},
    )
    def city_risk(city: str):
        if city not in CITY_NAMES:
            raise HTTPException(404, "未知城市")
        raise HTTPException(501, "城市综合健康风险尚未建立科研计算结果；目前仅提供单元 AT 年龄组风险和全市市辖区合并区域 HI")

    @app.get("/api/v1/units/{unit_id}/hourly", response_model=Forecast[Hourly])
    def hourly(unit_id: str):
        return read(unit_id, "current", "hourly", Hourly)

    @app.get("/api/v1/units/{unit_id}/daily", response_model=Forecast[Daily])
    def daily(unit_id: str):
        return read(unit_id, "current", "daily", Daily)

    @app.get("/api/v1/units/{unit_id}/health-risk", response_model=Forecast[HealthRisk])
    def health_risk(unit_id: str):
        return read(unit_id, "processed", "health_risk", HealthRisk, "at")

    @app.get("/api/v1/units/{unit_id}/heat-index/hourly", response_model=Forecast[HIHourly])
    def hi_hourly(unit_id: str):
        return read(unit_id, "processed", "heat_index_hourly", HIHourly, "hi")

    @app.get("/api/v1/units/{unit_id}/heat-index/daily", response_model=Forecast[HIDaily])
    def hi_daily(unit_id: str):
        return read(unit_id, "processed", "heat_index_daily", HIDaily, "hi")

    return app


app = create_app()
