# CountyFlow

CountyFlow 是县域物流异常识别与智能调度系统，通过异步八 Agent 工作流形成可恢复、可解释、可审计的调度结果。

## Role-based light frontend

CountyFlow 现在使用同一个白色企业级 React SPA，为调度员、调度主管、系统运维、审计员和系统管理员提供不同的默认工作空间。导航和前端路由由 `AuthenticatedPrincipal` 的 permissions 过滤，角色只决定默认 Landing 与信息排序；FastAPI 仍是直接 API 请求的最终授权边界。

`local` / `docker-dev` 提供显式标注的 `DEV AUTH` 角色预览。每次切换都从后端取得 server-issued development session，浏览器不能自行添加角色或权限。Production build 不包含角色切换 UI，Production backend 也拒绝 development-session contract。

白色主题覆盖 App Shell、Sidebar、Topbar、Cards、Tables、Dialogs、Graph 和 Monitoring。API 模式只显示真实数据或明确的 `EMPTY`、`NOT EXPOSED`、`UNAVAILABLE`、`NO PERMISSION` 状态，不用静态 KPI 或 Demo fallback 冒充实时结果。浏览器验收证据见 `docs/verification/frontend-role-ui/frontend-role-light-review.md`。

## Architecture

```text
Frontend
  → FastAPI
  → Redis Streams
  → Worker-1 / Worker-2
  → Intake → Entity Memory → Graph Memory → Environment → Capacity → Routing → Dispatch → Audit
  → MySQL Shared Memory Control Plane / Qdrant Vector Memory / Neo4j Graph Memory
  → AsyncRedisSaver Checkpoint / Thread Registry / Runtime Override
  → Redis Task Events
  → WebSocket
  → Frontend
```

八 Agent 顺序为 Intake、Entity Memory、Graph Memory、Environment、Capacity、Routing、Dispatch、Audit。FastAPI 只负责接单、只读 Runtime Thread 查询和 WebSocket，不在请求中同步执行完整 Graph。

## 新平县离线虚拟沙盘

教师反馈对应的演示完全使用仓库生成的虚拟数据，不接入高德、实时路况或真实车辆系统。固定沙盘包含 8 个站点、18 个道路节点、26 条道路边、10 名司机、12 辆车辆和 12 张运单。

- 车辆故障：`DEMO-ORDER-001` 的 `V-001` 故障后，系统从 12 辆候选车中计算并选择 `V-005` 与司机 `D-003`，接驳边为 `E20`，接驳 2.80 公里、6 分钟，评分 93.4；所有未入选车辆保留排除原因。
- 道路堵塞：`DEMO-ORDER-005` 的 `E04` 阻断后，Dijkstra（`DIJKSTRA_V1`，结果携带道路网络版本）把原路线 `E01→E02→E03→E04→E05` 重算为 `E01→E06→E07→E08→E09`，新路线不含 `E04`，里程增加 3.20 公里、耗时增加 4 分钟。

真实异步栈验收入口为 `scripts/test-offline-fleet-routing.ps1`，它只通过公开 API 提交/查询业务任务，再用 MySQL/Redis 做事后一致性断言。2026-09-08 当前工作区缺少被忽略的 `.docker.env`，该真实栈验收状态为 `BLOCKED BY ENVIRONMENT`；网络拦截的 Playwright UI 回归 2/2 通过，只证明浏览器提交、展示和刷新恢复，不替代真实服务验收。

## Quick Start

Windows 双击 [一键启动.bat](./一键启动.bat)。Local 模式启动：

- Frontend
- FastAPI Backend
- SQLite

Local 模式不启动 Real Redis、Worker、MySQL 或 Qdrant Server。因此异步 POST 在 Redis 不可用时会诚实返回 `503 QUEUE_UNAVAILABLE`，不能视为完整 E2E。

## Full Runtime

Windows 双击 [一键启动完整版.bat](./一键启动完整版.bat)。该入口需要 Docker，并声明 MySQL、Redis 8、Qdrant、Neo4j、Migration、Backend、两个独立 Worker、Frontend、Prometheus 和 Grafana，共 11 个服务；Migration 完成后保留 10 个长运行服务。

当前 Docker Profile 明确为 `docker-dev`：使用 Real Redis/MySQL/Qdrant/Neo4j Server，并启用签名 development JWT、五角色 RBAC、Redis rate limit/revocation、一次性 WebSocket ticket 与安全审计；Graph 使用 deterministic embedding、Docker development environment、InMemory Capacity 和 InMemory Route Catalog，仅用于 Functional E2E，不代表生产真实 AI。

该 Runtime 已在真实 Docker Engine 上完成 Functional E2E：MySQL 8.4、Redis 8.2.9 AOF、Qdrant、Neo4j Community、两个独立 Worker、官方 AsyncRedisSaver、精确 checkpoint 恢复、浏览器提交/WebSocket 重放与持久化均已验证。Prometheus 从 Backend、Worker-1、Worker-2 的内部 `:9100` 采集，Grafana 使用仓库内置 datasource、dashboard 与 SLO/alert rules；浏览器只访问需要 `monitor:read` 的固定 Observability Read API，不直接访问 Prometheus。`scripts/test-docker.ps1` 可重复执行完整门禁；V2-G1 专项入口为 `scripts/test-observability.ps1`，V2-G2 安全入口为 `scripts/test-security.ps1`，认证性能入口为 `scripts/test-security-performance.ps1`。

实时 Monitoring 与冻结验收基线严格分区：`LIVE`/`STALE`/`UNAVAILABLE`/`NO_PERMISSION` 来自实时 API，Top-1 98%、Graph 20/20、15/15 与 Locust 等值始终标注为 `VERIFIED ACCEPTANCE BASELINE`，不会伪装成实时 Prometheus 指标。API 模式失败时不会回退 Mock。

## Runtime Profiles

| Profile | 用途 | Provider 约束 |
|---|---|---|
| `local` | Windows 本地界面/API/SQLite 开发 | 不启动完整异步链路 |
| `test` | 自动化测试 | 允许 Fake、fakeredis、SQLite、Qdrant `:memory:` |
| `docker-dev` | 可重复 Functional E2E | 明确允许 deterministic/InMemory Provider |
| `production` | 未来真实 Provider 运行 | 拒绝 FakeEmbedding、开发 Environment、InMemory Capacity/Route；当前真实 wiring 未实现并会 fail fast |

`GET /health` 返回不含凭据的 Runtime 标签。它不会返回 API Key、密码、完整 Database URL、Redis URL 或 Qdrant URL。

## Verification Levels

- **Unit/Fake Verified**：pytest/Vitest、SQLite、fakeredis、Qdrant `:memory:` 或 Mock HTTP。
- **Local Verified**：当前机器上的 Frontend、FastAPI、SQLite 和构建门禁。
- **Real Docker Verified**：真实 Compose 的 Redis/MySQL/Qdrant/双 Worker/浏览器 Functional E2E 已达到。该结论不包含生产 AI Provider 或正式性能 SLA。

## Current Test Baseline

- Backend：2026-09-08 Ruff PASS；直接 pytest 使用工作区 `--basetemp` 完整收集 994 项，982 PASS、12 个显式 opt-in Real Store 测试因当前环境未启用而跳过。
- Frontend：2026-09-08 lint PASS（0 errors，2 个既有 Fast Refresh 结构 warning）；54 个 Vitest 文件、250 项测试 PASS；TypeScript 和 production build PASS。
- Windows 总门禁：`powershell -ExecutionPolicy Bypass -File scripts/check.ps1`。

V2-G2 当前安全验收：100 个聚焦后端安全测试、18 个聚焦前端鉴权测试、无手工令牌登录与 5/5 角色浏览器场景、7/7 已认证业务浏览器回归均 PASS；认证开启的 50-user/60-second Locust 为 QPS 278.998、P95 270ms、意外错误率 0%。最终矩阵见 `docs/verification/v2-g2/v2-g2-final-acceptance.md`。

V2-F2 当前验收：五角色 server-issued Role Preview、权限导航/直接 URL 防护、主管真实 Runtime Intervention、白色 computed surfaces、1366/1440/1920、12 张真实截图均由 Playwright PASS；安全浏览器回归 6/6、已认证业务回归 7/7、可观测性浏览器回归 3/3。页面级证据与明确的 `NOT EXPOSED` / deferred 边界见 `docs/verification/frontend-role-ui/frontend-role-light-review.md`。

Real Redis 8、MySQL、Qdrant、Neo4j、Docker 与三次真实 Worker kill/XAUTOCLAIM 精确 checkpoint 恢复均为 **VERIFIED**。冻结验收基线（不是实时监控值）包括：15/15 黑盒、真实 Embedding Top-1 49/50（98%）与 Top-3 50/50、Graph 20/20（P95 10.354ms）、Runtime Override 50/50、Checkpoint 5/5、Worker Recovery 最大 4.824 秒，以及 Locust 最低 QPS 400.071、最高 P95 200ms、Error Rate 0%。商业天气 API 与生产 LLM 仍不在当前 `docker-dev` 验收范围内。
