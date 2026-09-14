from pathlib import Path
import sys

import pandas as pd


# ============================================================
# 1. 项目路径
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "forecast_runs"
)

CURRENT_DIR = (
    PROJECT_ROOT
    / "data"
    / "current"
)

HOURLY_OUTPUT = (
    CURRENT_DIR
    / "beijing_center_forecast_hourly.csv"
)


# ============================================================
# 2. 找到最新一份原始预报
# ============================================================

def find_latest_raw_forecast():

    if not RAW_DIR.exists():
        raise FileNotFoundError(
            f"原始预报文件夹不存在：\n{RAW_DIR}"
        )

    files = sorted(
        RAW_DIR.glob("forecast_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            "没有找到 forecast_*.csv 原始预报文件"
        )

    latest_file = files[0]

    print(
        "使用最新原始预报："
    )
    print(
        latest_file
    )

    return latest_file


# ============================================================
# 3. 读取并检查原始数据
# ============================================================

def load_raw_forecast(file_path):

    df = pd.read_csv(
        file_path
    )

    required_columns = {
        "update_time",
        "forecast_time",
        "point_id",
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_ms",
        "area_weight",
        "source",
        "model",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"原始预报缺少字段：{missing}"
        )

    print()
    print(
        "========== 原始数据检查 =========="
    )

    print(
        f"原始记录数：{len(df)}"
    )

    point_count = (
        df["point_id"]
        .nunique()
    )

    hour_count = (
        df["forecast_time"]
        .nunique()
    )

    print(
        f"格点数：{point_count}"
    )

    print(
        f"预报小时数：{hour_count}"
    )

    if point_count != 30:
        raise ValueError(
            f"预期30个格点，实际为 {point_count}"
        )

    if hour_count != 168:
        raise ValueError(
            f"预期168小时，实际为 {hour_count}"
        )

    if len(df) != 30 * 168:
        raise ValueError(
            f"预期5040条记录，实际为 {len(df)}"
        )

    weather_columns = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_ms",
        "area_weight",
    ]

    if df[
        weather_columns
    ].isna().any().any():

        raise ValueError(
            "原始预报存在关键字段缺失"
        )

    print(
        "原始数据检查：通过"
    )

    return df


# ============================================================
# 4. 检查每个小时的权重
# ============================================================

def check_hourly_weights(df):

    weight_sum_by_hour = (
        df.groupby(
            "forecast_time"
        )[
            "area_weight"
        ]
        .sum()
    )

    min_weight_sum = (
        weight_sum_by_hour.min()
    )

    max_weight_sum = (
        weight_sum_by_hour.max()
    )

    print()
    print(
        "========== 权重检查 =========="
    )

    print(
        "每小时权重和最小值："
        f"{min_weight_sum:.10f}"
    )

    print(
        "每小时权重和最大值："
        f"{max_weight_sum:.10f}"
    )

    if (
        (weight_sum_by_hour - 1.0)
        .abs()
        .max()
        > 1e-6
    ):
        raise ValueError(
            "部分小时 area_weight 总和不约等于1"
        )

    print(
        "每小时权重检查：通过"
    )


# ============================================================
# 5. 面积加权
# ============================================================

def calculate_center_average(df):

    print()
    print(
        "========== 计算六城区代表气象量 =========="
    )

    # --------------------------------------------------------
    # 对每个格点：
    #
    # 气象变量 × 面积权重
    # --------------------------------------------------------

    df = df.copy()

    df["temperature_weighted"] = (
        df["temperature_c"]
        * df["area_weight"]
    )

    df["rh_weighted"] = (
        df["relative_humidity_pct"]
        * df["area_weight"]
    )

    df["wind_weighted"] = (
        df["wind_speed_ms"]
        * df["area_weight"]
    )

    # --------------------------------------------------------
    # 每个 forecast_time 求和
    # --------------------------------------------------------

    hourly = (
        df.groupby(
            "forecast_time",
            as_index=False,
        )
        .agg(
            temperature_c=(
                "temperature_weighted",
                "sum",
            ),

            relative_humidity_pct=(
                "rh_weighted",
                "sum",
            ),

            wind_speed_ms=(
                "wind_weighted",
                "sum",
            ),

            point_count=(
                "point_id",
                "nunique",
            ),

            weight_sum=(
                "area_weight",
                "sum",
            ),
        )
    )

    # --------------------------------------------------------
    # 更新时间
    # --------------------------------------------------------

    update_times = (
        df["update_time"]
        .dropna()
        .unique()
    )

    if len(update_times) == 0:
        raise ValueError(
            "没有 update_time"
        )

    update_time = (
        update_times[0]
    )

    hourly.insert(
        0,
        "update_time",
        update_time,
    )

    # --------------------------------------------------------
    # 数据源
    # --------------------------------------------------------

    source_values = (
        df["source"]
        .dropna()
        .unique()
    )

    model_values = (
        df["model"]
        .dropna()
        .unique()
    )

    source = (
        source_values[0]
        if len(source_values) > 0
        else "unknown"
    )

    model = (
        model_values[0]
        if len(model_values) > 0
        else "unknown"
    )

    hourly["source"] = (
        source
    )

    hourly["model"] = (
        model
    )

    hourly["spatial_method"] = (
        "six_district_area_weighted_mean"
    )

    # --------------------------------------------------------
    # 时间排序
    # --------------------------------------------------------

    hourly[
        "forecast_time"
    ] = pd.to_datetime(
        hourly[
            "forecast_time"
        ]
    )

    hourly = (
        hourly.sort_values(
            "forecast_time"
        )
        .reset_index(
            drop=True
        )
    )

    print(
        f"已生成 {len(hourly)} 个小时"
    )

    return hourly


# ============================================================
# 6. 结果质量控制
# ============================================================

def quality_control(hourly):

    print()
    print(
        "========== 中心城区 hourly QC =========="
    )

    print(
        f"行数：{len(hourly)}"
    )

    print(
        "开始时间：",
        hourly[
            "forecast_time"
        ].iloc[0],
    )

    print(
        "结束时间：",
        hourly[
            "forecast_time"
        ].iloc[-1],
    )

    # --------------------------------------------------------
    # 168小时
    # --------------------------------------------------------

    if len(hourly) != 168:
        raise ValueError(
            f"预期168行，实际 {len(hourly)} 行"
        )

    # --------------------------------------------------------
    # 每小时30点
    # --------------------------------------------------------

    if not (
        hourly[
            "point_count"
        ] == 30
    ).all():

        raise ValueError(
            "存在不足30个格点的小时"
        )

    # --------------------------------------------------------
    # 权重
    # --------------------------------------------------------

    max_weight_error = (
        hourly[
            "weight_sum"
        ]
        .sub(1.0)
        .abs()
        .max()
    )

    print(
        "最大权重误差："
        f"{max_weight_error:.12f}"
    )

    if max_weight_error > 1e-6:
        raise ValueError(
            "存在权重和异常小时"
        )

    # --------------------------------------------------------
    # 缺失值
    # --------------------------------------------------------

    weather_columns = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_ms",
    ]

    missing = (
        hourly[
            weather_columns
        ]
        .isna()
        .sum()
    )

    print()
    print(
        "缺测："
    )

    print(
        missing
    )

    if missing.sum() != 0:
        raise ValueError(
            "中心城区 hourly 存在缺测"
        )

    # --------------------------------------------------------
    # 时间连续
    # --------------------------------------------------------

    time_diff = (
        hourly[
            "forecast_time"
        ]
        .diff()
        .dropna()
    )

    if not (
        time_diff
        == pd.Timedelta(hours=1)
    ).all():

        raise ValueError(
            "hourly 时间不是连续1小时"
        )

    # --------------------------------------------------------
    # 基本物理范围
    # --------------------------------------------------------

    t_min = hourly[
        "temperature_c"
    ].min()

    t_max = hourly[
        "temperature_c"
    ].max()

    rh_min = hourly[
        "relative_humidity_pct"
    ].min()

    rh_max = hourly[
        "relative_humidity_pct"
    ].max()

    wind_min = hourly[
        "wind_speed_ms"
    ].min()

    wind_max = hourly[
        "wind_speed_ms"
    ].max()

    print()
    print(
        f"中心城区温度："
        f"{t_min:.3f} ～ {t_max:.3f} ℃"
    )

    print(
        f"中心城区RH："
        f"{rh_min:.3f} ～ {rh_max:.3f} %"
    )

    print(
        f"中心城区风速："
        f"{wind_min:.3f} ～ {wind_max:.3f} m/s"
    )

    if rh_min < 0 or rh_max > 100:
        raise ValueError(
            "RH 超出0～100%"
        )

    if wind_min < 0:
        raise ValueError(
            "出现负风速"
        )

    print()
    print(
        "中心城区 hourly QC：通过"
    )


# ============================================================
# 7. 保存
# ============================================================

def save_hourly(hourly):

    CURRENT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 保存前重新转成标准时间字符串
    output_df = (
        hourly.copy()
    )

    output_df[
        "forecast_time"
    ] = output_df[
        "forecast_time"
    ].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    output_df.to_csv(
        HOURLY_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        "========== 文件保存 =========="
    )

    print(
        "中心城区逐小时预报已保存："
    )

    print(
        HOURLY_OUTPUT
    )


# ============================================================
# 8. 主程序
# ============================================================

def main():

    print()
    print(
        "=============================================="
    )

    print(
        " 北京六中心城区逐小时面积加权"
    )

    print(
        "=============================================="
    )

    try:

        raw_file = (
            find_latest_raw_forecast()
        )

        raw_df = (
            load_raw_forecast(
                raw_file
            )
        )

        check_hourly_weights(
            raw_df
        )

        hourly = (
            calculate_center_average(
                raw_df
            )
        )

        quality_control(
            hourly
        )

        save_hourly(
            hourly
        )

        print()
        print(
            "=============================================="
        )

        print(
            " 面积加权完成"
        )

        print(
            "=============================================="
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

        sys.exit(1)


if __name__ == "__main__":
    main()