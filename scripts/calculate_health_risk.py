from pathlib import Path
import math
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DAILY_FILE = (
    PROJECT_ROOT
    / "data"
    / "current"
    / "beijing_center_forecast_daily.csv"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "beijing_center_health_risk.csv"
)

RESULT_COLUMNS = [
    "update_time", "forecast_date", "tmean_c", "tmax_c", "rhmean_pct",
    "vmean_ms", "vapor_pressure_hpa", "at_c", "risk_0_64",
    "risk_65_plus", "hour_count", "is_complete_day", "source", "model",
]


def load_daily():

    if not DAILY_FILE.exists():
        raise FileNotFoundError(
            f"没有找到：{DAILY_FILE}"
        )

    df = pd.read_csv(DAILY_FILE)

    required = {
        "update_time",
        "forecast_date",
        "tmean_c",
        "tmax_c",
        "rhmean_pct",
        "vmean_ms",
        "hour_count",
        "is_complete_day",
        "source",
        "model",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"daily 文件缺少字段：{missing}"
        )

    # 兼容 CSV 中 True / False 字符串
    if df["is_complete_day"].dtype != bool:
        df["is_complete_day"] = (
            df["is_complete_day"]
            .astype(str)
            .str.lower()
            .map({
                "true": True,
                "false": False
            })
        )

    print("daily 文件读取成功")
    print(f"总日期数：{len(df)}")

    return df


def calculate_at(t, rh, wind):

    # 水汽压
    e = (
        (rh / 100.0)
        * 6.105
        * math.exp(
            17.27 * t
            / (237.7 + t)
        )
    )

    # Apparent Temperature
    at = (
        t
        + 0.33 * e
        - 0.70 * wind
        - 4.00
    )

    return e, at


def classify_0_64(at):

    if at < 33.6:
        return "未进入热效应风险分级"

    elif at < 35.2:
        return "低风险"

    elif at < 37.2:
        return "中风险"

    else:
        return "高风险"


def classify_65_plus(at):

    if at < 34.5:
        return "未进入热效应风险分级"

    elif at < 35.9:
        return "低风险"

    elif at < 37.6:
        return "中风险"

    else:
        return "高风险"


def calculate_health_risk(df):

    result = df.copy()

    result["vapor_pressure_hpa"] = float("nan")
    result["at_c"] = float("nan")

    result["risk_0_64"] = "不完整日，不进入正式分级"
    result["risk_65_plus"] = "不完整日，不进入正式分级"

    for index, row in result.iterrows():

        if not row["is_complete_day"]:
            continue

        t = row["tmean_c"]
        rh = row["rhmean_pct"]
        wind = row["vmean_ms"]

        e, at = calculate_at(
            t,
            rh,
            wind
        )

        result.at[
            index,
            "vapor_pressure_hpa"
        ] = e

        result.at[
            index,
            "at_c"
        ] = at

        result.at[
            index,
            "risk_0_64"
        ] = classify_0_64(at)

        result.at[
            index,
            "risk_65_plus"
        ] = classify_65_plus(at)

    return result


def quality_control(df):

    print()
    print("========== 健康风险 QC ==========")

    complete = df[
        df["is_complete_day"] == True
    ]

    incomplete = df[
        df["is_complete_day"] == False
    ]

    print(
        f"完整日期数：{len(complete)}"
    )

    print(
        f"不完整日期数：{len(incomplete)}"
    )

    if complete.empty:
        raise ValueError(
            "没有完整自然日可用于 AT 计算"
        )

    # AT 缺失
    if complete["at_c"].isna().any():
        raise ValueError(
            "完整日期存在 AT 缺失"
        )

    # 无穷值检查
    if not complete["at_c"].map(
        math.isfinite
    ).all():
        raise ValueError(
            "AT 中存在无穷值"
        )

    at_min = complete[
        "at_c"
    ].min()

    at_max = complete[
        "at_c"
    ].max()

    print(
        f"AT范围：{at_min:.3f} ～ {at_max:.3f} ℃"
    )

    print()
    print("0–64岁风险统计：")

    print(
        complete[
            "risk_0_64"
        ].value_counts()
    )

    print()
    print("≥65岁风险统计：")

    print(
        complete[
            "risk_65_plus"
        ].value_counts()
    )

    # 检查不完整日没有被误分级
    if not incomplete.empty:

        wrong_0_64 = (
            incomplete[
                "risk_0_64"
            ]
            != "不完整日，不进入正式分级"
        ).any()

        wrong_65 = (
            incomplete[
                "risk_65_plus"
            ]
            != "不完整日，不进入正式分级"
        ).any()

        if wrong_0_64 or wrong_65:
            raise ValueError(
                "存在不完整日期被错误分级"
            )

    print()
    print("健康风险 QC：通过")


def save_result(df):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = df[RESULT_COLUMNS]

    output.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("结果已保存：")
    print(OUTPUT_FILE)


def main():

    try:

        print()
        print(
            "======================================"
        )

        print(
            " 北京六中心城区高温健康风险计算"
        )

        print(
            "======================================"
        )

        daily = load_daily()

        result = calculate_health_risk(
            daily
        )

        quality_control(
            result
        )

        save_result(
            result
        )

        print()
        print(
            "======================================"
        )

        print(
            " 健康风险计算完成"
        )

        print(
            "======================================"
        )

    except Exception as e:

        print()
        print("程序运行失败：")
        print(type(e).__name__)
        print(str(e))

        sys.exit(1)


if __name__ == "__main__":
    main()
