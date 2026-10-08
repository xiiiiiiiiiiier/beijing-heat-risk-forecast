# Render 部署和自动更新

## 已准备的链路

GitHub Actions 完成第一链 → 校验 45 个单元、141 个文件 → 提交整批 CSV → Render 自动部署该提交 → 启动前再次校验 → 健康检查成功后切换流量。

API 直接使用每次部署自带的仓库文件，不在运行中逐个覆盖 CSV。新部署失败时，Render 保留已有的成功部署；第一次部署失败则没有可用服务。旧数据超过 24 小时会被 API 标记为陈旧。

城市综合健康风险接口 `/api/v1/cities/{city}/risk` 目前只返回 501 和“尚未实现”的说明，不读取或生成城市风险数据。本次接口变更由 GitHub `main` 提交触发现有 Render 服务的 On Commit 部署；该服务已在 Render 页面手动创建，修改 `render.yaml` 不会自动改变其设置。现有 45 单元、141 份 API 结果文件的校验范围不因此改变。

选择重新部署来更新数据，适用于当前每日约四次更新和较小的数据集。每次会消耗构建额度；未来数据规模或更新频率显著增长时再考虑独立存储。当前不需要数据库、后台轮询器或部署密钥。

## 首次配置

1. 将本分支的 API、render.yaml、验证脚本和工作流合并到 main。首次上线之前，运行完整测试和 python -m scripts.validate_api_snapshot。
2. 登录 Render，以 GitHub 连接此仓库。要启用自动部署必须连接 Git 提供商，仅用 Public Git Repository URL 方式不具备自动部署。
3. New → Blueprint，选择此仓库和 main，使用根目录 render.yaml；已有同名服务时先检查并更新已有服务，不重复创建。
4. 配置为 Python Web Service。构建命令 pip install -r requirements-api.txt；启动命令 python -m uvicorn api:app --host 0.0.0.0 --port $PORT；健康检查 /health；自动部署 On Commit。
5. VALIDATE_SNAPSHOT_ON_START=1；CORS_ORIGINS 填网页的精确 origin，多个以逗号分隔。RENDER_GIT_COMMIT 由 Render 提供，勿自行填旧提交号。
6. 记录 Render 实际分配的 HTTPS 地址。成功后用 /api/v1/status 核对 snapshot_revision、45 个单元、141 个文件、六市更新时间；再实际调用一个 AT 和一个 HI 接口。

render.yaml 暂选 free 以便试运行，尚不代表已创建服务或授权付费。免费服务 15 分钟无流量后休眠，下次请求唤醒大约需要一分钟；正式持续响应需自行选择不休眠的付费实例并确认费用。免费实例还受构建额度等限制。

## 更新验收与异常处理

等下一轮第一链成功提交 CSV，确认 Render 产生自动部署，并对照 /api/v1/status.snapshot_revision 与该数据提交号。该公网端到端核对完成后，才可以把“数据自动更新衔接”标为已验收。

不要把 On Commit 改成 After CI Checks Pass 而不检查机器人提交是否有检查记录：本仓库使用 GitHub Actions 提交数据，此类提交未必触发新的 Actions 检查。整批校验分别在提交前和实例启动前执行。

新版本校验失败：查看 Actions 或 Render 日志中的具体单元/文件，修复第一链输出后重新提交。不要关闭 VALIDATE_SNAPSHOT_ON_START 绕过检查。部署回滚：在 Render 选此前成功提交回滚，并检查自动部署设置，防止错误版本被再次部署；回滚后的旧数据仍显示实际更新时间。

## 参考

- https://render.com/docs/deploys
- https://render.com/docs/blueprint-spec
- https://render.com/docs/free
