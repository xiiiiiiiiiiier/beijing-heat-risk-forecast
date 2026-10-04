# 前端接口合同 v1

范围：六市 45 单元；39 个非 urban 单元支持 AT，6 个 urban 单元支持 HI。以 /api/v1/cities/{city}/units 的 indicators 为前端可选项依据。当前不为 core 单元生成 HI，也不为 urban 单元生成 AT。

机器可读合同为 [api-openapi.json](api-openapi.json)，线上 /openapi.json 提供运行版本。现有 CSV 数值、风险标签和科学阈值不由 API 改写。

## 查询流程

1. GET /api/v1/cities 获取城市。
2. GET /api/v1/cities/{city}/units 获取空间单元及 indicators。
3. GET /api/v1/units/{unit_id}/hourly 或 /daily 获取气象。
4. 对 at 单元获取 /health-risk，同时返回 risk_0_64 和 risk_65_plus；前端选择人群只控制展示。
5. 对 hi 单元获取 /heat-index/hourly 或 /heat-index/daily。
6. GET /api/v1/status 核对 45 个单元、141 个文件与各市更新时间。

## 字段和显示

所有预报响应都有 unit、timezone、data_kind、snapshot_revision、update_time、data_age_hours、is_stale、rows。snapshot_revision 在 Render 中等于部署的 Git 提交号，本地没有配置时为 null。时间包含 +08:00，日期为 YYYY-MM-DD。

| 字段 | 单位或含义 |
| --- | --- |
| temperature_c、tmean_c、tmax_c、at_c、hi_c、hi_max_c | 摄氏度 |
| relative_humidity_pct、rhmean_pct | 相对湿度百分比 |
| wind_speed_ms、vmean_ms | 米每秒 |
| vapor_pressure_hpa | 百帕 |
| hour_count、is_complete_day | 自然日小时数和完整性 |
| risk_0_64、risk_65_plus | 第一链原始年龄组风险标签 |
| hi_class、effect_on_body | 第一链 HI 分级和说明 |

前端必须同时展示数据时间和“预报”性质。is_stale=true（超过 24 小时）时显示“数据更新延迟”；不得把过期数据标为最新。该阈值是运维提示，不是健康风险阈值。

不完整日照常展示气象和完整性提示；AT 的空数值是 null，不能改为 0，也不能将“未进入热效应风险分级”改为“无风险”。时序图应把 null 作为缺失值。

同一单元跨多个接口组合时，比较 snapshot_revision 和 update_time；不同则重新获取整组结果。不同城市的 update_time 可以相差几分钟，整批允许的获取跨度上限是 2 小时。该上限用于发现上一轮城市混入新轮次，不改变科学计算。

## 错误与浏览器访问

错误正文为 {"detail":"说明"}。未知城市或单元返回 404；单元不支持请求的 AT/HI 返回 422；文件缺失、损坏或整批检查失败返回 503。前端对 503 显示“数据暂不可用”，保留上次有效展示但标记为旧数据，避免无限重试。/health 仅是进程存活检查。

浏览器跨域使用 CORS_ORIGINS 的精确域名白名单，逗号分隔，不带路径或末尾斜杠。本地默认 http://localhost:3000；Render 配置初始允许现有 GitHub Pages 域名。Next.js 上线后添加其正式域名。无 cookie 凭据授权。

兼容性：v1 保留现有字段名称与类型；破坏性变更另开 v2。新增字段允许前端忽略。新增科研单元或指标需同时更新合同、单元清单与验证。
