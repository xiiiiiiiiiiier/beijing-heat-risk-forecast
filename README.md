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

仓库中的三个结果 CSV 是提交时的快照，不会因为本地计划任务运行而自动更新 GitHub。`website/` 目前尚无网页；仓库创建本身也不会让别人看到持续更新的网页。后续需实现展示页面，并把更新任务部署到持续运行的服务器或自动化平台。

低于文献热效应低风险起点时，结果标为“未进入热效应风险分级”，并不表示“无风险”。历史 ERA5-Land 试运行与本仓库的未来预报是不同数据链。
