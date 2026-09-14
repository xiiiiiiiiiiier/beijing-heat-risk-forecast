# 北京中心城区高温健康风险预报

本项目对北京东城、西城、朝阳、海淀、丰台、石景山六区联合区域计算未来 7 天逐小时气象代表值、每日体感温度（AT）和两个年龄组的热效应风险分级。数据来自 Open-Meteo Forecast API 的 ECMWF IFS 预报；30 个格点的面积权重保存在 `data/static/forecast_points.csv`。Open-Meteo 将不同预报时效统一为逐小时序列。

## 运行

在项目根目录安装依赖并运行：

```powershell
python -m pip install -r requirements.txt
python scripts/update_all.py
```

程序依次获取预报、计算六区面积加权均值、按北京时间自然日聚合、计算 AT 与 0–64 岁及 ≥65 岁风险。每次原始预报另存于 `data/raw/forecast_runs/`；该目录的 CSV 不进入 Git。最新结果为：

- `data/current/beijing_center_forecast_hourly.csv`：未来 168 小时气象数据。
- `data/current/beijing_center_forecast_daily.csv`：北京时间每日气象数据，含 `hour_count` 和 `is_complete_day`。
- `data/processed/beijing_center_health_risk.csv`：每日 AT 与两年龄组风险。

仓库根目录的 `index.html` 是静态展示页，直接读取上述三个 CSV。`.github/workflows/update-forecast.yml` 每 6 小时运行一次计算链，成功后将新 CSV 提交到仓库。GitHub 定时任务可能晚于设定时间启动，请以网页上的数据更新时间为准。公开网址由 GitHub Pages 提供。

低于文献热效应低风险起点时，结果标为“未进入热效应风险分级”，并不表示“无风险”。历史 ERA5-Land 试运行与本仓库的未来预报是不同数据链。
