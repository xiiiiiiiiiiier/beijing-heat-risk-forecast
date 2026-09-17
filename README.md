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

## 六市研究单元

北京原有六区联合预报链保留，作为回归基准。另有六市各一份主城区联合结果及其余 33 个市辖区各一份独立结果，共 39 个计算单元。具体区名、行政代码和格点数见 `data/static/units/manifest.json`。当前网页仍只展示北京原有结果；新增 CSV 是供后续网站接入的数据，不表示已有 39 个页面。

`scripts/update_units.py` 按城市合并相同的 O1280 格点请求，逐轮核对 Open-Meteo 返回坐标（距理论中心不超过 2 米且互不重复），然后按各单元自己的权重计算逐小时值、北京时间日值和两年龄组风险。固定参数是 `models=ecmwf_ifs`、`cell_selection=nearest`、`elevation=nan`。每城市的原始取数保存在 `data/raw/forecast_runs/<city>/`，不提交 Git；最新结果在 `data/current/units/` 和 `data/processed/units/`。单独更新一个城市：

```powershell
python scripts/update_units.py --city tianjin
```

不带 `--city` 时更新全部六市。GitHub Actions 每六小时执行北京原流程和六市流程，全部成功后才提交 CSV 并部署。某次失败时不会把本轮不完整输出发布到网站。

空间输入来自与北京现有边界相同的第三方 [pamaforce/geojson WGS84 数据](https://github.com/pamaforce/geojson)，原始市级文件保存在 `data/boundary_sources/`。源文件使用 GB 编码；边界不是官方法定界线。`scripts/build_spatial.py` 按 O1280 实际格点中心、等面积投影下的最近中心 Voronoi 单元与研究区相交面积生成各单元权重；北京主城区继续直接使用 `data/static/forecast_points.csv` 权重。仅在边界、模型或格点选择规则改变并完成复核后重新生成：

```powershell
python -m pip install -r requirements-spatial.txt
python scripts/build_spatial.py
```

新增单元采用《草稿.docx》的市辖区清单；县和县级市没有纳入。第三方边界与官方法定界线可能不同，正式科研发布前应核定范围和边界版本。ERA5-Land 的格点或权重不能用于本预报链。
