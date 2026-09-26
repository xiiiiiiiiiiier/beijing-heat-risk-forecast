# 京津冀六市高温健康风险预报科研计算链第一阶段完成报告

## 1. 报告说明

本报告记录北京、天津、石家庄、唐山、邯郸、保定六市高温健康风险预报科研计算链第一阶段的完成状态、统一口径、软件结构、验证结果和当前边界。报告以仓库 `main` 分支稳定提交 `c77da7247fbd0493c3d84c24dcb0a5094fdcb2dd` 为基线。

本阶段的目标是建立可由 Python 直接调用、可批量更新、可重复验证的六市统一科研计算入口。在尚未完成来源核验的事项上，本报告只陈述仓库当前实现，不将其表述为已有正式文献依据、规划依据或官方边界来源。

## 2. 阶段范围

本阶段已覆盖：

- 六市独立 Python 单元入口；
- Open-Meteo ECMWF IFS 逐小时预报获取；
- 格点面积加权、北京时间自然日聚合、表观温度（AT）计算；
- `0–64` 岁和 `≥65` 岁两年龄组风险输出；
- 全部市辖区联合区域的热指数（HI）输出；
- 六市批处理与 GitHub Actions 自动更新；
- 单元识别、完整计算链、历史结果回归和原有城市链回归测试。

本阶段不包含 Web API、前端、数据库、历史数据分析或城市脆弱性模块，也不代表空间边界及 `core` 划分依据已经完成正式科研审定。

## 3. 六市完成状态

| 城市 | Python 单元入口 | 默认 AT 单元 | 阶段状态 |
|---|---|---|---|
| 北京 | `run_beijing_forecast()` | `beijing_core` | 已完成并纳入测试 |
| 天津 | `run_tianjin_forecast()` | `tianjin_core` | 已完成并纳入测试 |
| 石家庄 | `run_shijiazhuang_forecast()` | `shijiazhuang_core` | 已完成并纳入测试 |
| 唐山 | `run_tangshan_forecast()` | `tangshan_core` | 已完成并纳入测试 |
| 邯郸 | `run_handan_forecast()` | `handan_core` | 已完成并纳入测试 |
| 保定 | `run_baoding_forecast()` | `baoding_core` | 已完成并纳入测试 |

六个公开入口均位于 `scripts/update_all.py`，并统一委托 `run_city_forecast()` 执行，不分别复制科研计算逻辑。入口接受 `unit_id`，也支持传入已获取的逐小时原始数据并通过 `save=False` 关闭文件写出，便于回归测试与后续系统集成。

## 4. 六市空间单元与 AT/HI 角色

当前仓库将每个城市的空间单元分为两类：

- `*_urban`：全部市辖区联合区域，仅进入 HI 计算，不作为六市单元入口的 AT 健康风险单元；
- `*_core` 和列出的独立区级单元：进入日尺度 AT 及两年龄组风险计算。

| 城市 | AT 与年龄组风险单元 | HI 单元 |
|---|---|---|
| 北京 | `beijing_core`、`beijing_110109`、`beijing_110111`、`beijing_110112`、`beijing_110113`、`beijing_110114`、`beijing_110115`、`beijing_110116`、`beijing_110117`、`beijing_110118`、`beijing_110119` | `beijing_urban` |
| 天津 | `tianjin_core`、`tianjin_120110`、`tianjin_120111`、`tianjin_120112`、`tianjin_120113`、`tianjin_120114`、`tianjin_120115`、`tianjin_120116`、`tianjin_120117`、`tianjin_120118`、`tianjin_120119` | `tianjin_urban` |
| 石家庄 | `shijiazhuang_core`、`shijiazhuang_130107`、`shijiazhuang_130109`、`shijiazhuang_130110`、`shijiazhuang_130111` | `shijiazhuang_urban` |
| 唐山 | `tangshan_core`、`tangshan_130204`、`tangshan_130208`、`tangshan_130209` | `tangshan_urban` |
| 邯郸 | `handan_core`、`handan_130406`、`handan_130407`、`handan_130408` | `handan_urban` |
| 保定 | `baoding_core`、`baoding_130607`、`baoding_130608`、`baoding_130609` | `baoding_urban` |

这里的“主城区”和“全部市辖区联合区域”是当前仓库中的计算单元名称。各城市 `core` 的正式科研或规划依据、边界版本及可引用来源仍须后续核验。

## 5. 统一计算链

六市 AT 健康风险计算共享以下链路：

1. `load_city()` 读取城市单元、格点和面积权重；
2. `fetch_city()` 通过 Open-Meteo 获取 ECMWF IFS 未来 7 天、共 168 个连续小时的气温、相对湿度和 10 米风速；
3. `weighted_hourly()` 按空间单元的面积权重汇总逐小时气象量；
4. `calculate_daily_weather()` 按北京时间自然日计算日平均气温、日最高气温、日平均相对湿度、日平均风速及小时完整性；
5. `calculate_health_risk()` 计算水汽压、AT，以及 `risk_0_64` 和 `risk_65_plus`；
6. 完成质量控制后，可写出逐小时、日尺度和健康风险 CSV。

调用关系可概括为：

```text
六市 run_*_forecast()
        ↓
run_city_forecast()
        ↓
格点获取/面积加权 → calculate_daily_weather() → calculate_health_risk()
```

批处理 `scripts/update_units.py` 复用相同的日尺度与健康风险函数。对 `*_urban` 单元，它转入 `heat_index_tables()` 生成 HI 逐小时和日尺度结果；对其他单元，则生成 AT 与年龄组风险结果。

## 6. 关键科研口径

### 6.1 预报源与时长

- 数据接口：Open-Meteo Forecast API；
- 模型参数：`ecmwf_ifs`（当前实现对应 ECMWF IFS HRES 链）；
- 预报长度：7 天，即 168 个连续小时；
- 气象变量：2 米气温、2 米相对湿度、10 米风速；
- 单元气象量：按已配置格点面积权重汇总。

### 6.2 时间与日尺度

- API 请求使用 `Asia/Shanghai`；
- 日聚合以北京时间自然日为边界；
- 每个自然日记录 `hour_count`；
- 仅 `hour_count == 24` 时，`is_complete_day` 为真；
- 不完整日保留气象聚合记录，但不进入正式风险分级。

### 6.3 健康风险输出

完整日结果包含水汽压 `vapor_pressure_hpa`、表观温度 `at_c`、`risk_0_64` 和 `risk_65_plus`。两个风险字段分别对应 `0–64` 岁和 `≥65` 岁人群。第一阶段没有修改 AT 公式、风险阈值、日尺度口径或 HI 计算方法。

## 7. 软件结构与复用关系

| 文件 | 第一阶段职责 |
|---|---|
| `scripts/update_all.py` | 提供六市公开入口和共享 `run_city_forecast()` |
| `scripts/update_units.py` | 六市批量获取、面积加权、按单元分派 AT/风险或 HI，并原子更新结果文件 |
| `scripts/calculate_daily_weather.py` | 统一的北京时间自然日聚合与 24 小时完整性判断 |
| `scripts/calculate_health_risk.py` | 统一的水汽压、AT、两年龄组风险和质量控制 |
| `scripts/heat_index.py` | `*_urban` 单元的 HI 结果生成 |
| `data/static/units/manifest.json` | 六市计算单元、区划代码和格点数量清单 |
| `data/static/units/*_points.csv` | 各计算单元格点及面积权重 |
| `tests/test_*_pipeline.py` | 六市入口、单元识别、完整链和回归测试 |

核心复用关系是：六市入口只负责绑定城市和默认单元，所有城市共同进入 `run_city_forecast()`；该共享入口继续调用唯一的 `calculate_daily_weather()` 和 `calculate_health_risk()`。因此，第一阶段没有为单个城市复制 AT、风险或日尺度科研计算代码。

## 8. 测试与回归验证

在稳定提交 `c77da7247fbd0493c3d84c24dcb0a5094fdcb2dd` 上：

- 完整测试结果为 **45/45 通过**；
- 六市各自的合法 AT 单元被明确识别；
- 各城市的 `*_urban`、`*_other` 和未知单元 ID 被 AT 单元入口明确拒绝；
- 测试覆盖逐小时输入、实际格点数量、面积加权、日尺度、AT 和两年龄组风险输出；
- 北京原有计算链及后续五市新增入口均保留回归验证；
- 已验证的新入口与仓库既有 CSV 结果差异约为 `1e-15` 量级，属于浮点计算或 CSV 往返误差；
- 风险标签、日期、小时数和完整日标记保持一致。

测试使用 `1e-12` 绝对容差核对数值结果；当前观测到的最大差异显著低于该容差。上述结论仅说明当前实现与仓库基准结果一致，不替代下一阶段的六市科研计算链总验收。

## 9. 自动更新链

`scripts/update_units.py` 支持两种运行方式：

- 不指定城市时，依次更新北京、天津、石家庄、唐山、邯郸、保定；
- 通过 `--city` 选择其中一个城市更新。

GitHub Actions 工作流 `.github/workflows/update-forecast.yml` 已接入六市批处理：安装依赖后先运行现有北京入口，再运行 `python scripts/update_units.py` 更新六市单元结果；有数据变化时提交最新 CSV，并准备和部署站点数据。定时任务按当前配置每日运行四次，也支持手动触发。

## 10. 已完成与待后续核验

### 10.1 已完成

- 六市统一 Python 单元入口；
- 共享的逐小时获取、面积加权、日尺度、AT 与风险计算链；
- AT 单元与 `urban`/HI 单元的程序分工；
- 168 小时预报和北京时间自然日完整性处理；
- `0–64` 岁与 `≥65` 岁风险输出；
- 六市批处理和 GitHub Actions 自动更新；
- 45 项自动测试及当前基准 CSV 回归验证。

### 10.2 待后续核验或建设

- GeoJSON 的正式来源、授权情况和行政区划版本；
- 各城市 `core` 划分的正式科研、统计或规划依据；
- 六市科研计算链总验收，包括跨城市口径、输入、空间单元、输出和异常处理的横向复核；
- FastAPI 服务层；
- Next.js 前端；
- PostgreSQL 数据层；
- 历史数据模块；
- 城市脆弱性模块。

在上述来源核验完成前，不应把当前 GeoJSON 或 `core` 定义描述为已获官方或文献确认。第一阶段完成状态也不意味着整个网站、数据平台或科研验证已经完成。

## 11. 当前稳定版本

- 仓库：`xiiiiiiiiiiier/beijing-heat-risk-forecast`
- 分支：`main`
- 第一阶段代码基线：`c77da7247fbd0493c3d84c24dcb0a5094fdcb2dd`
- 基线提交说明：`feat: add unified Baoding spatial unit forecast entry`
- 基线测试状态：`45/45` 通过

## 12. 下一阶段唯一优先任务

下一阶段的唯一优先任务是：**六市科研计算链总验收**。

该验收应先于 FastAPI、Next.js、PostgreSQL、历史数据和城市脆弱性模块。验收重点包括六市空间单元定义、AT 与 HI 分工、数据源与 168 小时输入、面积权重、北京时间自然日与完整 24 小时口径、AT 和年龄组风险输出、回归基准、批处理及自动更新的一致性，并对尚未确认的 GeoJSON 来源和 `core` 划分依据形成明确的核验清单与结论。
