# 第二链 FastAPI 第一版

本版从第一链生成的 CSV 提供只读 JSON 服务。基于 2026-10-04 克隆的 main 提交 d5e14052ff7251c5e45b058fa06f45ab60b521ce。

## 设计与实施范围

沿用现有 manifest 的 45 个单元。39 个非 urban 单元提供 AT 两年龄组风险，6 个 urban 单元提供 HI。所有单元提供小时和日气象。API 不执行实时取数或重新计算：页面请求不会触发耗时的外部气象请求，也不会更改第一链公式。

实现顺序：读取清单与 CSV、建立输出字段模型、公开只读接口、核对全部 45 个单元的结果、增加错误与陈旧数据验证。实现集中在 api.py；第一链继续用现有脚本产生结果。

## 本地运行

在仓库根目录（建议 Python 3.11 或更新版本）运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/docs 可以展开接口并试用，OpenAPI 位于 /openapi.json。

| GET 路径 | 含义 |
| --- | --- |
| /health | 服务进程存活，不代表数据新鲜或部署成功 |
| /api/v1/cities | 六市及单元数 |
| /api/v1/cities/{city}/units | 城市单元及可用 indicators |
| /api/v1/units/{unit_id}/hourly | 小时气象 |
| /api/v1/units/{unit_id}/daily | 日气象和完整日标记 |
| /api/v1/units/{unit_id}/health-risk | AT 与两年龄组风险，仅非 urban |
| /api/v1/units/{unit_id}/heat-index/hourly | 小时 HI，仅 urban |
| /api/v1/units/{unit_id}/heat-index/daily | 日最大 HI，仅 urban |

示例：/api/v1/units/tianjin_core/health-risk 或 /api/v1/units/tianjin_urban/heat-index/daily。

## 数据约定

预报响应包含 unit、timezone、data_kind、update_time、data_age_hours、is_stale、rows。字段含义和科学数值沿用 CSV；温度单位为摄氏度、湿度为百分比、风速为米每秒。时间转为带 +08:00 的 ISO 字符串，日期保留 YYYY-MM-DD。布尔和数字以 JSON 对应类型返回，不完整日缺失的 AT 数值为 null，原有风险说明保留。

超过 24 小时未更新标记 is_stale=true，这是 API 的运维提示，不是科研分级阈值。即使旧数据仍可读取，也不能用 /health 宣称预报已更新。每个接口读取一个 CSV 文件，拒绝其中混合批次、重复时间、非有限数字、无效字段或错误的日完整性标记。多个接口之间不保证整批快照一致，前端组合结果时必须比较 update_time；不一致时重试。

未知城市/单元返回 404；不支持的 AT/HI 与单元组合返回 422；清单/数据缺失、为空或损坏返回 503。请求只接受清单中的单元 ID，不接受文件路径。

## 更新和部署边界

API 读取本地 data 目录，每次请求读取当前文件。GitHub 上产生新 CSV 不会自动同步到独立 API 服务器，后续部署必须配置数据同步或重新部署，并校验整批结果后再切换。GitHub Pages 只能运行现有静态页面，不能承载此 Python 服务。本版仅完成本地服务，尚未发布到公网。

截至本次检查，GitHub Actions run 37210813177 的结论为 success；用户截图展示的此前失败不能据此认定已定位原因。最新成功也不证明历史失败根因已修复。

## 验证

```powershell
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

接口测试逐一比对 45 单元的 141 个结果文件，另覆盖未知单元、AT/HI 范围、缺失/损坏文件、陈旧数据、不完整日和 OpenAPI。第一链回归测试同时运行。测试不会调用外部天气 API 更新预报。

本次本地验证：Python 3.12 环境共 51 项测试通过，其中新增 API 测试 5 项（含全部单元和文件的子检查）。另启动 Uvicorn，通过实际 HTTP 确认 /health、/docs 和天津主城区风险接口正常。未执行线上部署；GitHub 的新增检查工作流需推送后才会运行。

## 2026-10-05 公网部署与后续核验

上文“尚未发布到公网”和“未执行线上部署”是第一版编写时的历史状态，现已变化。FastAPI 已在 Render 免费 Web Service `beijing-heat-risk-api` 上线，公开地址为 https://beijing-heat-risk-api.onrender.com，接口文档为 `/docs`，整批数据状态为 `/api/v1/status`。服务在 Render 页面手动创建并连接 GitHub `main`，配置了 On Commit 自动部署、Python 3.12.10、新加坡地区、`/health` 健康检查、`VALIDATE_SNAPSHOT_ON_START=1` 和现有 GitHub Pages 域名的 CORS 白名单。根目录 `render.yaml` 是配置记录，并未作为 Blueprint 创建此服务；后续若改动部署设置，需核对 Render 页面中的实际配置。

定时更新运行 [37303138079](https://github.com/xiiiiiiiiiiier/beijing-heat-risk-forecast/actions/runs/37303138079) 成功后，数据提交 `1b89056381f22813e997909ec4d611d9c920ff8e` 已部署到 Render。本次核对时，公网 `/api/v1/status` 返回相同的 `snapshot_revision`、45 个单元、141 份结果文件和六市更新时间，均为 `is_stale=false`；后续任何 `main` 提交（包括文档提交）都会触发新部署并改变快照号，数据时间未必改变。公网天津主城区 `/health-risk` 与天津 `urban` 的 `/heat-index/daily` 各返回 7 行结果。`/health`、`/docs`、`/api/v1/cities` 返回 200，不支持的 AT/HI 组合返回 422，未知单元返回 404。允许的 GitHub Pages origin 收到跨域响应头；一次 PowerShell 请求曾触发 Cloudflare 校验页，而普通 HTTP 请求随后正常返回 JSON，网页接入时仍需实际浏览器核对。

本次以仓库已有 `.venv` 执行完整测试，55 项通过；最新数据快照校验为 45 个单元、141 份文件。现有静态网页尚未改为调用这些接口，下一步按 [前端接口合同](api_contract_v1.md) 接入六市与研究单元选择、AT/HI 和数据时间提示。Render 免费实例闲置后会休眠，首次请求可能延迟 50 秒以上。

## 2026-10-08 城市综合健康风险接口预留

`GET /api/v1/cities/{city}/risk` 仅占用将来的接口路径，已知城市返回 501“尚未实现”，未知城市返回 404。当前没有城市综合健康风险的科研结果、数值或等级；现有 AT 年龄组风险与每市全部市辖区合并区域的 HI 都不能充当综合风险。该预留接口不改变六市自动更新、141 份结果文件或现有查询接口。
