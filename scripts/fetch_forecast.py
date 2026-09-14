from pathlib import Path
from datetime import datetime
import sys

import pandas as pd
import requests


# ============================================================
# 1. 项目路径
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

POINTS_FILE = (
    PROJECT_ROOT
    / "data"
    / "static"
    / "forecast_points.csv"
)

RAW_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "forecast_runs"
)


# ============================================================
# 2. Open-Meteo API 参数
# ============================================================

API_URL = "https://api.open-meteo.com/v1/forecast"

# ECMWF IFS HRES，约9 km
MODEL = "ecmwf_ifs"

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
]

FORECAST_DAYS = 7

TIMEZONE = "Asia/Shanghai"


# ============================================================
# 3. 读取并检查 forecast_points.csv
# ============================================================

def load_forecast_points():

    print("正在读取 forecast_points.csv ...")

    if not POINTS_FILE.exists():
        raise FileNotFoundError(
            f"没有找到文件：\n{POINTS_FILE}"
        )

    points = pd.read_csv(POINTS_FILE)

    # --------------------------------------------------------
    # 必须存在的字段
    # --------------------------------------------------------

    required_columns = {
        "point_id",
        "latitude",
        "longitude",
        "intersect_area_km2",
        "area_weight",
        "api_latitude",
        "api_longitude",
    }

    missing_columns = (
        required_columns
        - set(points.columns)
    )

    if missing_columns:
        raise ValueError(
            "forecast_points.csv 缺少字段："
            f"{missing_columns}"
        )

    # --------------------------------------------------------
    # 行数
    # --------------------------------------------------------

    if len(points) != 30:
        raise ValueError(
            f"预期30个有效格点，实际为 {len(points)}"
        )

    # --------------------------------------------------------
    # 缺失值
    # --------------------------------------------------------

    check_columns = [
        "point_id",
        "latitude",
        "longitude",
        "intersect_area_km2",
        "area_weight",
        "api_latitude",
        "api_longitude",
    ]

    if points[check_columns].isna().any().any():
        raise ValueError(
            "forecast_points.csv 中存在空值"
        )

    # --------------------------------------------------------
    # point_id重复检查
    # --------------------------------------------------------

    if points["point_id"].duplicated().any():
        raise ValueError(
            "forecast_points.csv 存在重复 point_id"
        )

    # --------------------------------------------------------
    # API格点重复检查
    # --------------------------------------------------------

    if points[
        ["api_latitude", "api_longitude"]
    ].duplicated().any():

        duplicated = points[
            points[
                ["api_latitude", "api_longitude"]
            ].duplicated(
                keep=False
            )
        ]

        print(duplicated)

        raise ValueError(
            "forecast_points.csv 存在重复 API 格点"
        )

    # --------------------------------------------------------
    # 权重合法性
    # --------------------------------------------------------

    if (points["area_weight"] <= 0).any():
        raise ValueError(
            "存在 area_weight <= 0 的格点"
        )

    weight_sum = points[
        "area_weight"
    ].sum()

    if abs(weight_sum - 1.0) > 1e-6:
        raise ValueError(
            "area_weight 总和异常："
            f"{weight_sum}"
        )

    # --------------------------------------------------------
    # 相交面积检查
    # --------------------------------------------------------

    if (
        points["intersect_area_km2"]
        <= 0
    ).any():

        raise ValueError(
            "存在相交面积 <= 0 的格点"
        )

    # --------------------------------------------------------
    # 输出结果
    # --------------------------------------------------------

    print()
    print(
        "========== forecast_points.csv QC =========="
    )

    print(
        f"有效格点数：{len(points)}"
    )

    print(
        "相交面积总和："
        f"{points['intersect_area_km2'].sum():.6f} km²"
    )

    print(
        f"权重和：{weight_sum:.10f}"
    )

    print(
        "API格点重复数：",
        points[
            ["api_latitude", "api_longitude"]
        ].duplicated().sum()
    )

    print(
        "forecast_points.csv QC：通过"
    )

    return points


# ============================================================
# 4. 调用 Open-Meteo
# ============================================================

def fetch_open_meteo(points):

    print()
    print(
        "========== 请求 Open-Meteo =========="
    )

    # --------------------------------------------------------
    # 这里特别注意：
    #
    # 不使用 latitude / longitude
    # 而使用已经核对好的：
    #
    # api_latitude
    # api_longitude
    #
    # --------------------------------------------------------

    latitudes = ",".join(
        points[
            "api_latitude"
        ].astype(str)
    )

    longitudes = ",".join(
        points[
            "api_longitude"
        ].astype(str)
    )

    # --------------------------------------------------------
    # 六城区全部位于北京时间
    # 多地点显式指定同一个 timezone
    # --------------------------------------------------------

    timezones = ",".join(
        [TIMEZONE] * len(points)
    )

    # --------------------------------------------------------
    # 禁用基于高程的额外统计降尺度
    #
    # 因为我们现在需要的是：
    #
    # 模式格点 → 面积权重
    #
    # 而不是API根据每个位置DEM再次调整温度。
    # --------------------------------------------------------

    elevations = ",".join(
        ["nan"] * len(points)
    )

    params = {

        "latitude":
            latitudes,

        "longitude":
            longitudes,

        "hourly":
            ",".join(
                HOURLY_VARIABLES
            ),

        "models":
            MODEL,

        "forecast_days":
            FORECAST_DAYS,

        "timezone":
            timezones,

        "wind_speed_unit":
            "ms",

        # 选择最近模式网格
        "cell_selection":
            "nearest",

        # 禁用高程统计降尺度
        "elevation":
            elevations,
    }

    print(
        f"请求格点数量：{len(points)}"
    )

    print(
        f"预报天数：{FORECAST_DAYS}"
    )

    print(
        f"模式：{MODEL}"
    )

    print(
        "变量："
        "temperature_2m, "
        "relative_humidity_2m, "
        "wind_speed_10m"
    )

    try:

        response = requests.get(
            API_URL,
            params=params,
            timeout=120,
        )

    except requests.RequestException as e:

        raise RuntimeError(
            "连接 Open-Meteo 失败："
            f"{e}"
        )

    # --------------------------------------------------------
    # HTTP错误
    # --------------------------------------------------------

    if response.status_code != 200:

        print()
        print(
            "Open-Meteo 返回错误："
        )

        print(
            response.text
        )

        raise RuntimeError(
            f"HTTP错误："
            f"{response.status_code}"
        )

    data = response.json()

    print(
        "Open-Meteo 请求成功"
    )

    return data


# ============================================================
# 5. API JSON 转换为 DataFrame
# ============================================================

def convert_to_dataframe(
    data,
    points
):

    print()
    print(
        "========== 整理 API 数据 =========="
    )

    # --------------------------------------------------------
    # 多地点请求应返回 list
    # 单地点时则可能返回 dict
    # --------------------------------------------------------

    if isinstance(data, dict):
        data = [data]

    if len(data) != len(points):

        raise ValueError(
            "API返回地点数量与"
            "forecast_points.csv 不一致："
            f"{len(data)} vs {len(points)}"
        )

    update_time = (
        datetime.now()
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )

    rows = []

    # --------------------------------------------------------
    # 一个 API location 对应 forecast_points 一行
    # --------------------------------------------------------

    for i, location in enumerate(data):

        point = points.iloc[i]

        hourly = location.get(
            "hourly"
        )

        if hourly is None:

            raise ValueError(
                f"{point['point_id']} "
                "没有 hourly 数据"
            )

        times = hourly.get(
            "time"
        )

        temperatures = hourly.get(
            "temperature_2m"
        )

        humidities = hourly.get(
            "relative_humidity_2m"
        )

        wind_speeds = hourly.get(
            "wind_speed_10m"
        )

        if (
            times is None
            or temperatures is None
            or humidities is None
            or wind_speeds is None
        ):

            raise ValueError(
                f"{point['point_id']} "
                "缺少预报变量"
            )

        # ----------------------------------------------------
        # 时间长度必须一致
        # ----------------------------------------------------

        lengths = [
            len(times),
            len(temperatures),
            len(humidities),
            len(wind_speeds),
        ]

        if len(
            set(lengths)
        ) != 1:

            raise ValueError(
                f"{point['point_id']} "
                f"变量长度不一致：{lengths}"
            )

        # ----------------------------------------------------
        # 转成长表
        # ----------------------------------------------------

        for (
            forecast_time,
            temperature,
            humidity,
            wind_speed,
        ) in zip(
            times,
            temperatures,
            humidities,
            wind_speeds,
        ):

            rows.append({

                "update_time":
                    update_time,

                "forecast_time":
                    forecast_time,

                "point_id":
                    point[
                        "point_id"
                    ],

                # -----------------------------
                # 正式空间格点
                # -----------------------------

                "grid_latitude":
                    point[
                        "latitude"
                    ],

                "grid_longitude":
                    point[
                        "longitude"
                    ],

                # -----------------------------
                # 实际 API 请求坐标
                # -----------------------------

                "api_request_latitude":
                    point[
                        "api_latitude"
                    ],

                "api_request_longitude":
                    point[
                        "api_longitude"
                    ],

                # -----------------------------
                # Open-Meteo实际返回位置
                # -----------------------------

                "api_return_latitude":
                    location.get(
                        "latitude"
                    ),

                "api_return_longitude":
                    location.get(
                        "longitude"
                    ),

                # -----------------------------
                # 气象变量
                # -----------------------------

                "temperature_c":
                    temperature,

                "relative_humidity_pct":
                    humidity,

                "wind_speed_ms":
                    wind_speed,

                # -----------------------------
                # 空间权重
                # -----------------------------

                "intersect_area_km2":
                    point[
                        "intersect_area_km2"
                    ],

                "area_weight":
                    point[
                        "area_weight"
                    ],

                # -----------------------------
                # 格点匹配信息
                # -----------------------------

                "api_offset_m":
                    point.get(
                        "api_offset_m",
                        None
                    ),

                "grid_row_north":
                    point.get(
                        "grid_row_north",
                        None
                    ),

                # -----------------------------
                # 数据来源
                # -----------------------------

                "source":
                    "Open-Meteo",

                "model":
                    MODEL,
            })

    df = pd.DataFrame(
        rows
    )

    print(
        f"整理完成，共 {len(df)} 条记录"
    )

    return df


# ============================================================
# 6. 原始预报质量控制
# ============================================================

def quality_control(
    df,
    points
):

    print()
    print(
        "========== 原始预报 QC =========="
    )

    expected_points = len(
        points
    )

    # --------------------------------------------------------
    # 有多少个不同预报时刻
    # --------------------------------------------------------

    forecast_times = (
        df[
            "forecast_time"
        ]
        .drop_duplicates()
        .sort_values()
    )

    hour_count = len(
        forecast_times
    )

    print(
        f"格点数：{expected_points}"
    )

    print(
        f"预报小时数：{hour_count}"
    )

    print(
        f"总记录数：{len(df)}"
    )

    print(
        "预报开始：",
        forecast_times.iloc[0]
    )

    print(
        "预报结束：",
        forecast_times.iloc[-1]
    )

    # --------------------------------------------------------
    # 正常目标：
    #
    # 30 × 168 = 5040
    # --------------------------------------------------------

    if hour_count != 168:

        raise ValueError(
            "预报小时数不是168："
            f"{hour_count}"
        )

    expected_rows = (
        expected_points
        * 168
    )

    if len(df) != expected_rows:

        raise ValueError(
            f"预期 {expected_rows} 条，"
            f"实际 {len(df)} 条"
        )

    # --------------------------------------------------------
    # 缺测
    # --------------------------------------------------------

    weather_columns = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_ms",
    ]

    missing = (
        df[
            weather_columns
        ]
        .isna()
        .sum()
    )

    print()
    print(
        "气象变量缺测："
    )

    print(
        missing
    )

    if missing.sum() != 0:

        raise ValueError(
            "气象变量存在缺测值"
        )

    # --------------------------------------------------------
    # 每小时必须完整包含30个点
    # --------------------------------------------------------

    points_per_hour = (
        df.groupby(
            "forecast_time"
        )[
            "point_id"
        ]
        .nunique()
    )

    if not (
        points_per_hour
        == expected_points
    ).all():

        bad_hours = (
            points_per_hour[
                points_per_hour
                != expected_points
            ]
        )

        print(
            bad_hours
        )

        raise ValueError(
            "存在格点数量不完整的预报小时"
        )

    # --------------------------------------------------------
    # 每个点必须168小时
    # --------------------------------------------------------

    hours_per_point = (
        df.groupby(
            "point_id"
        )[
            "forecast_time"
        ]
        .nunique()
    )

    if not (
        hours_per_point
        == 168
    ).all():

        print(
            hours_per_point
        )

        raise ValueError(
            "部分格点不足168小时"
        )

    # --------------------------------------------------------
    # 权重
    # --------------------------------------------------------

    weights = (
        df[
            [
                "point_id",
                "area_weight"
            ]
        ]
        .drop_duplicates()
    )

    weight_sum = weights[
        "area_weight"
    ].sum()

    print()
    print(
        f"权重和：{weight_sum:.10f}"
    )

    if abs(
        weight_sum - 1.0
    ) > 1e-6:

        raise ValueError(
            "原始预报中的权重和异常"
        )

    # --------------------------------------------------------
    # 数值基本物理检查
    # --------------------------------------------------------

    t_min = df[
        "temperature_c"
    ].min()

    t_max = df[
        "temperature_c"
    ].max()

    rh_min = df[
        "relative_humidity_pct"
    ].min()

    rh_max = df[
        "relative_humidity_pct"
    ].max()

    wind_min = df[
        "wind_speed_ms"
    ].min()

    wind_max = df[
        "wind_speed_ms"
    ].max()

    print()
    print(
        f"温度范围："
        f"{t_min:.3f} ～ {t_max:.3f} ℃"
    )

    print(
        f"RH范围："
        f"{rh_min:.3f} ～ {rh_max:.3f} %"
    )

    print(
        f"风速范围："
        f"{wind_min:.3f} ～ {wind_max:.3f} m/s"
    )

    if rh_min < 0 or rh_max > 100:

        raise ValueError(
            "相对湿度超出0～100%"
        )

    if wind_min < 0:

        raise ValueError(
            "出现负风速"
        )

    # --------------------------------------------------------
    # API返回坐标检查
    # --------------------------------------------------------

    api_locations = (
        df[
            [
                "point_id",
                "api_request_latitude",
                "api_request_longitude",
                "api_return_latitude",
                "api_return_longitude",
            ]
        ]
        .drop_duplicates()
    )

    print()
    print(
        "API返回唯一地点数：",
        len(
            api_locations[
                [
                    "api_return_latitude",
                    "api_return_longitude",
                ]
            ].drop_duplicates()
        )
    )

    # --------------------------------------------------------
    # 时间连续性
    # --------------------------------------------------------

    parsed_times = pd.to_datetime(
        forecast_times
    )

    time_diff = (
        parsed_times
        .diff()
        .dropna()
    )

    if not (
        time_diff
        == pd.Timedelta(
            hours=1
        )
    ).all():

        raise ValueError(
            "预报时间不是连续1小时间隔"
        )

    print()
    print(
        "原始预报 QC：通过"
    )

    print(
        "目标检查结果："
    )

    print(
        f"{expected_points} 个格点"
    )

    print(
        "168 个北京时间小时"
    )

    print(
        f"{expected_rows} 条记录"
    )

    print(
        "关键变量缺测 = 0"
    )


# ============================================================
# 7. 保存原始预报
# ============================================================

def save_raw_forecast(
    df
):

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    output_file = (
        RAW_DIR
        / (
            "forecast_"
            f"{timestamp}.csv"
        )
    )

    df.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        "========== 文件保存 =========="
    )

    print(
        "原始预报已保存："
    )

    print(
        output_file
    )

    return output_file


# ============================================================
# 8. 主程序
# ============================================================

def main():

    print()
    print(
        "=============================================="
    )

    print(
        " 北京六中心城区 ECMWF 未来7天预报获取"
    )

    print(
        "=============================================="
    )

    try:

        # 1.
        points = (
            load_forecast_points()
        )

        # 2.
        api_data = (
            fetch_open_meteo(
                points
            )
        )

        # 3.
        raw_df = (
            convert_to_dataframe(
                api_data,
                points
            )
        )

        # 4.
        quality_control(
            raw_df,
            points
        )

        # 5.
        output_file = (
            save_raw_forecast(
                raw_df
            )
        )

        print()
        print(
            "=============================================="
        )

        print(
            " 本轮预报获取成功"
        )

        print(
            "=============================================="
        )

        print()

        print(
            "下一步文件："
        )

        print(
            output_file
        )

    except Exception as e:

        print()
        print(
            "=============================================="
        )

        print(
            " 程序运行失败"
        )

        print(
            "=============================================="
        )

        print()

        print(
            type(e).__name__
        )

        print(
            str(e)
        )

        sys.exit(
            1
        )


if __name__ == "__main__":
    main()