# 京津冀六市高温预报与健康风险研究

本项目持续生成北京、天津、石家庄、唐山、邯郸、保定六市的未来气象预报及相关热风险研究结果。全部结果按 **45 个研究单元**分别保存为 CSV，自动任务约每六小时更新一次。数据来自 Open-Meteo Forecast API 的 ECMWF IFS 预报，是模式预报和研究计算结果，不是实况观测，也不代表个人实际暴露。

## 成果速览

| 成果 | 数量 | 文件位置 | 内容 |
| --- | ---: | --- | --- |
| 逐小时气象 | 45 份 | [`data/current/units/`](data/current/units/) | 每单元未来 168 小时的气温、相对湿度、风速及格点和权重信息 |
| 逐日气象 | 45 份 | [`data/current/units/`](data/current/units/) | 每单元 7 天的平均气温、最高气温、平均湿度、平均风速和日完整性 |
| 每日 AT 与年龄组风险 | 39 份 | [`data/processed/units/`](data/processed/units/) | 日尺度体感温度（AT）、0–64 岁及 ≥65 岁热效应风险分级 |
| 全市联合区域 HI | 12 份 | [`data/processed/units/`](data/processed/units/) | 六市各一份逐小时热指数（HI）和一份逐日最高 HI、等级与可能影响 |
| 北京主城区兼容结果 | 3 份 | [`data/current/`](data/current/)、[`data/processed/`](data/processed/) | 原北京六城区联合预报的小时、日值及 AT 风险文件 |

以上是 **144 份 CSV 文件**。城市及研究单元文件名、区域范围对照见[六市数据文件索引](data/current/units/README.md)；研究单元格点数、区划代码和基础信息见 [`data/static/units/manifest.json`](data/static/units/manifest.json)。北京、天津、石家庄、唐山、邯郸、保定各有一个 `urban`（全市市辖区联合区域）和一个 `core`（主城区联合区域）；其余研究单元以六位行政区代码命名。单元代表值按区域权重计算，不同范围不可简单相加。

**查看方式：**[在线网页](https://xiiiiiiiiiiier.github.io/beijing-heat-risk-forecast/)目前重点展示北京主城区的交互图表；其余城市和研究单元的全部结果已纳入仓库与 Pages 发布文件，可从上表目录或仓库文件索引查看、下载。网页显示范围不影响自动更新和 CSV 成果的覆盖范围。

## 指标说明

- **气象：** Open-Meteo 提供 ECMWF IFS 的逐小时 2 米气温、2 米相对湿度和 10 米风速。逐日数据按北京时间（UTC+8）汇总，并记录小时数及是否为完整自然日。
- **AT 与健康风险：** 对 39 个非 `urban` 单元计算日尺度 Apparent Temperature（AT）和两个年龄组热效应风险。风险等级按项目所引用的文献口径输出；“未进入热效应风险分级”仅表示低于所用分级起点，不表示“无风险”。各研究单元结果在 `*_health_risk.csv` 文件中。
- **HI：** 仅对每市 `urban` 全部市辖区联合区域计算 NOAA Heat Index：逐小时结果及当日最高值、发生时间、分类和可能身体影响。HI 与 AT 风险是不同指标；不完整日不作正式分级。HI 基于阴凉环境下的气温和湿度，未纳入日晒、个人体质或活动量。
- **时间与来源：** CSV 中 `update_time` 是本轮更新时间，`forecast_time` 和 `forecast_date` 分别是预报时刻和北京时间预报日期。`hour_count`、`is_complete_day` 用来检查预报日是否完整；边缘时段可能是不完整日。方法、数据来源和适用限制见[网站与研究流程说明](网站介绍.md)及[阶段报告](docs/six_city_forecast_pipeline_stage1_report.md)。

## 自动更新与本地运行

GitHub Actions 约每六小时运行北京原有预报流程及六市流程；全部步骤成功后提交最新 CSV 并部署 GitHub Pages。失败的更新不会发布为新一轮完整成果。定时任务实际开始时间可能有延迟，请查看 CSV 的 `update_time` 或 Actions 运行记录。

正式更新流程对取数超时、连接异常以及 HTTP 408、429、500、502、503、504 最多尝试 3 次。临时 HTTP 故障依次等待 15、30 秒，429 限流每次等待 61 秒，连接异常依次等待 5、10 秒；日志会记录重试原因。参数或权限等其它 HTTP 错误不自动重试，数据缺失、格点不匹配及时间不连续仍阻止发布。有限重试可减少临时服务故障造成的失败，但无法保证持续中断时仍能完成更新。

更新北京原有主城区结果：

```powershell
python -m pip install -r requirements.txt
python scripts/update_all.py
```

更新全部六市研究单元：

```powershell
python scripts/update_units.py
```

只更新一座城市（例如天津）：

```powershell
python scripts/update_units.py --city tianjin
```

每轮原始预报保存在 `data/raw/forecast_runs/`，不提交到 Git。六市空间权重和边界输入的构建流程见 [`scripts/build_spatial.py`](scripts/build_spatial.py) 及 [`requirements-spatial.txt`](requirements-spatial.txt)。当前行政区边界使用第三方数据，不是法定界线；边界版本、研究范围和适用性应在正式科研发布前核定。

## 2026-10-04 第二链 FastAPI 进度

新增只读 FastAPI 服务，直接读取第一链 CSV：六市及单元列表、小时/日气象、39 个非 urban 单元的 AT 两年龄组风险、6 个 urban 单元的小时/日 HI。原有科研脚本和静态页面继续保留。服务标明数据更新时间、北京时间及超过 24 小时的陈旧状态。

```powershell
python -m pip install -r requirements-api.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/docs 试用接口。完整接口、数据合同、安装与验证方法见 [第二链说明](docs/fastapi_stage2.md)。本版为本地服务，尚未部署公网；独立服务器的数据同步仍需配置，GitHub Pages 无法运行 Python API。

开发检查使用 `python -m pip install -r requirements-test.txt` 后执行 `python -m unittest discover -s tests -v`。新增独立测试工作流在代码变更时检查科研链与 API；现有定时预报工作流保留。

### 接口合同和云端更新准备

[v1 接口合同](docs/api_contract_v1.md) 和 [Render 部署说明](docs/render_deployment.md) 已补齐。根目录 render.yaml 定义试运行服务，第一链提交 CSV 前及云端启动前都执行整批检查。Render 连接 GitHub 后，On Commit 自动部署使代码和 CSV 以同一提交进入服务；/api/v1/status 可检查部署版本和六市数据时间。实际云服务仍须在 Render 账号中创建并验收，配置文件存在不代表已上线。

### 2026-10-05 公网部署与自动更新验收

上述“仅本地运行、尚未上线”记录的是 2026-10-04 的阶段状态。现在 FastAPI 已作为 Render 免费 Web Service 上线：[接口文档](https://beijing-heat-risk-api.onrender.com/docs)、[数据状态](https://beijing-heat-risk-api.onrender.com/api/v1/status)。服务连接本仓库 `main`，使用 On Commit 自动部署、`/health` 健康检查和启动时整批数据校验。服务是在 Render 页面手动创建的；`render.yaml` 保留部署配置参考，日后修改该文件不会自动修改这项已创建服务的设置。

截至本次核对，GitHub Actions 定时更新运行 [37303138079](https://github.com/xiiiiiiiiiiier/beijing-heat-risk-forecast/actions/runs/37303138079) 成功；仓库最新数据提交与当时线上的 `snapshot_revision` 均为 `1b89056381f22813e997909ec4d611d9c920ff8e`。后续任何 `main` 提交（包括文档提交）都会触发新部署并改变快照号，数据时间未必改变。线上状态返回六市、45 个研究单元、141 份 API 结果文件，六市数据未标记为过期；天津主城区 AT 风险和天津 urban 日 HI 接口均返回预报。项目环境下完整测试为 55/55 通过。免费实例闲置后会休眠，首次请求可能较慢。现有静态网页仍主要展示北京主城区，六市页面尚未接入该 API。

### 2026-10-08 城市综合健康风险接口预留

城市综合健康风险的科研方法和结果尚未完成。`GET /api/v1/cities/{city}/risk` 对六个已知城市明确返回 501“尚未实现”，未知城市返回 404；它不提供风险数值或等级。已有的单元 AT 年龄组风险、每市全部市辖区合并区域 HI 均不能代替城市综合健康风险。接口说明见 [v1 合同](docs/api_contract_v1.md)。
