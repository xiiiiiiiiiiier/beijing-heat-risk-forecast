"""Refresh the forecast and its derived CSV files in order."""

from pathlib import Path
import os
import subprocess
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "fetch_forecast.py",
    "calculate_center_average.py",
    "calculate_daily_weather.py",
    "calculate_health_risk.py",
)
OUTPUTS = (
    "data/current/beijing_center_forecast_hourly.csv",
    "data/current/beijing_center_forecast_daily.csv",
    "data/processed/beijing_center_health_risk.csv",
)


def main():
    total_start = perf_counter()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    for number, script in enumerate(SCRIPTS, 1):
        print(f"[{number}/4] {script}：开始", flush=True)
        start = perf_counter()
        try:
            result = subprocess.run([sys.executable, ROOT / "scripts" / script], cwd=ROOT, env=env)
        except OSError as exc:
            print(f"[{number}/4] {script}：失败（{exc}，耗时 {perf_counter() - start:.1f} 秒）", flush=True)
            return 1
        elapsed = perf_counter() - start
        if result.returncode != 0:
            print(f"[{number}/4] {script}：失败（退出码 {result.returncode}，耗时 {elapsed:.1f} 秒）", flush=True)
            return result.returncode
        print(f"[{number}/4] {script}：成功（耗时 {elapsed:.1f} 秒）", flush=True)

    missing = False
    for relative_path in OUTPUTS:
        path = ROOT / relative_path
        valid = path.is_file() and path.stat().st_size > 0
        print(f"{'存在且非空' if valid else '缺失或为空'}：{path}", flush=True)
        missing |= not valid
    if not missing:
        print(f"本轮更新完成，总耗时 {perf_counter() - total_start:.1f} 秒", flush=True)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
