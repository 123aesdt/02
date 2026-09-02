# CountyFlow 最终事实基线

> 文档性质：最终总结文档的唯一事实源（Single Source of Truth）
> 审计日期：2026-09-01（Asia/Shanghai）
> 审计方法：以当前代码、配置、测试与原始验收证据为准；旧总结仅作为线索，不作为结论。
> 适用范围：CountyFlow / 县域物流异常识别与智能调度系统当前工作区。
> 变更范围：在既有事实基线上新增司机异常上报、自动创建 AI 调度任务、调度中心收口及相关测试；未扩展照片、GPS 或生产 Provider 范围。

## 1. 结论口径

本项目已经形成一套可部署、可恢复、可审计的异步县域物流异常识别与智能调度工程原型。核心链路由 FastAPI、Redis Streams、Worker、LangGraph、MySQL、Qdrant、Neo4j、WebSocket 和 React 组成；运行时线程、稳定检查点、人工覆盖、共享记忆、权限、限流与可观测性均有真实代码和自动化测试支撑。

它还不能被描述为“开箱即用的生产系统”。当前全量 Docker 组合是 `docker-dev`：Embedding 使用 deterministic fake provider，Capacity 与 Routing 使用 in-memory provider；生产运行配置会主动拒绝未完成的 Provider wiring。灾备备份、恢复、校验、演练与 RPO/RTO 证据不存在。2026-09-01 已使用现有 `.docker.env` 重建 migration、backend、双 worker 与 frontend，当前容器健康且司机上报 Playwright spec 1/1 通过；真实依赖专项集成测试与性能压测未全部重跑。

## 2. 事实状态定义

| 状态 | 含义 |
|---|---|
| VERIFIED | 当前代码、静态配置或本轮实际执行的测试直接证明 |
| HISTORICAL VERIFIED | 仓库内存在可追溯原始证据，但本轮未重新执行 |
| NOT VERIFIED | 当前审计条件下无法重新验证；不等于功能不存在 |
| NOT EXPOSED | 后端数据或能力存在，但当前 UI/公共工作区未暴露 |
| DEFERRED | 明确未实现或延期，不得包装为已完成 |

## 3. 审计约束与异常

- Git 仓库当前显示 `No commits yet on master`，没有可用历史基线用于区分此前阶段提交。
- 工作树在本轮开始前已有大量 staged、untracked 与 mixed 状态；本轮保持这些用户内容不变。
- 根目录真实 `.env` 被忽略，但其中 development JWT secret 长度不满足当前最小 32 字符约束。
- 因该本地环境值，直接按 Makefile 默认方式执行后端 `pytest` 在收集阶段出现 15 个错误。
- 使用仅对测试进程生效的 `AUTHENTICATION_PROVIDER=disabled` 后，本轮后端测试通过：850 passed、7 skipped。
- 历史及本轮 pytest 临时目录存在 Windows ACL 拒绝访问，`rg`/Ruff 会告警，但不影响已完成测试结果。
- Docker Compose 配置解析在提供 `.docker.env` 时成功；不提供时会因必填安全配置缺失而失败，这是预期的 fail-fast 行为。
- Docker Compose 不提供环境文件时仍会按设计 fail-fast；使用现有 `.docker.env` 后已完成重建，backend health 为 ok，MySQL、Redis、Qdrant、Neo4j 及业务容器处于运行状态。

## 4. 项目定位

一句话定位：CountyFlow 是面向县域物流异常处置的异步、可恢复、可人工干预、可审计的智能调度工程原型。

核心业务问题：

1. 将订单、司机、车辆、路线、天气、道路等多源上下文组织为可执行调度任务。
2. 通过多 Agent 有序评估异常、历史经验、环境、运力与路线。
3. 在外部依赖失败、Worker 重启或并发干预时保持状态可恢复与结果不重复。
4. 允许授权人员在稳定边界修改车辆状态，并让后续节点读取同一份检查点事实。
5. 将事实、投影、调度、人工决策与安全事件保留为可追溯审计记录。

## 5. 当前目录与职责

| 路径 | 当前职责 |
|---|---|
| `backend/app/api/v1/` | FastAPI 路由、请求/响应 schema、鉴权依赖 |
| `backend/app/agents/` | 8 个单一职责 LangGraph 节点 |
| `backend/app/graph/` | 图构建、GraphState、依赖注入 |
| `backend/app/workers/` | Redis Streams 消费、重试、ACK、DLQ |
| `backend/app/runtime_threads/` | Runtime Thread 元数据、检查点推进、恢复 |
| `backend/app/runtime_overrides/` | 稳定边界人工覆盖及对账 |
| `backend/app/shared_memory/` | 共享事实控制面、投影、恢复与冲突策略 |
| `backend/app/memory/` | Qdrant Entity-Relation 向量记忆 |
| `backend/app/graph_memory/` | Neo4j 图记忆与模式 |
| `backend/app/security/` | 身份、权限、限流、撤销、WS ticket、脱敏、审计 |
| `backend/app/observability/` | 指标、探针、日志关联、查询服务 |
| `frontend/src/` | React 白色 App Shell、角色工作区、业务页面、状态语义 |
| `monitoring/` | Prometheus 规则与 Grafana provisioning |
| `loadtests/` | Locust 全链路与安全压测 |
| `benchmarks/` | 向量与图记忆基准数据集 |
| `docs/verification/` | 分阶段验收报告与原始输出 |
| `infra/` | 基础设施辅助配置 |

## 6. 端到端生产形态设计

设计链路：

`React → FastAPI → MySQL task creation → Redis Streams XADD → Worker XREADGROUP → LangGraph → MySQL/Qdrant/Neo4j/external environment → Redis event history/pub-sub → WebSocket/status query → React`

关键边界：

- API handler 只验证、创建任务、发布队列并返回 `task_id`，不在请求线程同步执行 LangGraph。
- Redis 不是长期事实源；MySQL 是订单、任务、调度、审计与控制面的 canonical source of truth。
- Qdrant 与 Neo4j 是检索/关系投影，不承担 canonical truth。
- Worker 仅在终态已经耐久化后 `XACK`。
- Runtime Thread 的最新 checkpoint pointer 在 MySQL，GraphState checkpoint body 在 Redis checkpointer。

## 7. 8-Agent LangGraph

确定顺序：

1. `intake`
2. `entity_memory`
3. `graph_memory`
4. `environment`
5. `capacity`
6. `routing`
7. `dispatch`
8. `audit`

### 7.1 节点事实

| Agent | 输入重点 | 输出/职责 | 降级与失败语义 |
|---|---|---|---|
| Intake Agent | task/order/anomaly/description | 校验、规范化、写 started_at | 缺失关键字段进入人工复核 |
| Entity Memory Agent | 规范化异常上下文 | Qdrant top-3 相似经验 | ProviderError 时空结果并记录 `MEMORY_RECALL_ERROR` |
| Graph Memory Agent | 实体、异常、路线等 | 写入并查询相关事实与多跳路径 | Neo4j 失败时安全降级为空并记录错误 |
| Environment Agent | 路线与外部环境 | 天气/道路评估 | async timeout、circuit breaker、静态路线 fallback |
| Capacity Agent | 司机、车辆、订单负载 | 运力可用性与容量等级 | Provider 错误转人工复核；故障车辆强制 unavailable |
| Routing Agent | 环境、运力、记忆 | 候选路线、推荐、采纳记忆 | 无安全路线时人工复核 |
| Dispatch Agent | 决策与实体版本 | 创建/更新 dispatch | `StaleDataError` 转并发冲突，不静默覆盖 |
| Audit Agent | 全状态与结果 | 耐久化审计证据 | 审计持久化失败阻止安全终态 ACK |

### 7.2 GraphState

GraphState 覆盖任务身份、订单/异常输入、规范化文本、向量记忆、图记忆、环境结果、车辆状态、运力结果、候选路线、推荐、调度结果、人工复核、错误、节点追踪、开始/完成时间及 checkpoint 相关字段。

车辆状态集合：`NORMAL`、`BROKEN`、`UNAVAILABLE`、`MAINTENANCE`。

## 8. LLM 与 Provider 边界

### 8.1 LLM

- 存在 `LLMProvider` Protocol。
- 存在 `OpenAICompatibleLLMProvider`，使用显式 async timeout。
- 存在仅用于测试的 `FakeLLMProvider`。
- 当前 8-Agent graph dependencies 没有注入或调用 LLMProvider。
- 因此“已具备 LLM 抽象和实现”是 VERIFIED；“当前调度由大模型推理驱动”是错误陈述。

### 8.2 Embedding

- 存在 `EmbeddingProvider` Protocol。
- 存在 OpenAI-Compatible Embedding 实现和 deterministic fake 实现。
- 当前 `docker-compose.yml` 明确设置 `EMBEDDING_PROVIDER=fake`、模型 `development-deterministic-128`。
- `backend/app/runtime.py` 实际构建 `FakeEmbeddingProvider`，并使用配置维度。
- 真实 OpenAI-Compatible embedding 只在独立交接/基准链路中验证过，不是当前 Docker runtime wiring。

### 8.3 Environment、Capacity、Routing

- Environment 有 HTTP provider、静态 fallback 与 circuit breaker。
- Capacity 只有 Protocol 与 `InMemoryCapacityProvider`。
- Routing 只有 Protocol 与 `InMemoryRouteProvider`。
- Docker runtime 的 Capacity 与 Routing 均为 in-memory。
- `runtime_profile=production` 会抛出错误：生产 Provider wiring 尚未实现。

## 9. Redis Streams 与 Worker

### 9.1 队列语义

- API 使用 `XADD` 发布稳定 `task_id` 与 `idempotency_key`。
- Worker 使用 consumer group 和 `XREADGROUP`。
- 仅在终态与审计耐久化后 `XACK`。
- pending recovery 使用 `XAUTOCLAIM`。
- 有界重试默认 3 次，指数退避从约 1 秒到最大 30 秒。
- 超出重试进入 DLQ。
- shutdown cancellation 不会错误 ACK 正在处理的消息。
- Docker 组合声明两个 Worker。

### 9.2 幂等与恢复

- Redis execution lock 防止并行处理同一任务。
- MySQL idempotency ledger 保存长期处理结论。
- 已终态任务重复投递时直接重放/ACK，不再次创建 dispatch。
- 该设计应称为“effectively-once business effect”，不是数学意义的 exactly-once delivery。

### 9.3 历史可靠性证据

- 消息丢失：0。
- 重复 delivery 未产生重复 dispatch/audit。
- 同一 idempotency key 的两次 HTTP 202 返回同一 task，唯一任务数 1。
- DLQ：delivery 3 次后原消息 ACK，pending 0。
- Redis AOF marker 在重启后保留。
- task stream pending 最终为 0。

## 10. Runtime Thread 与 Checkpoint

### 10.1 双层存储

- MySQL `runtime_threads`：线程 canonical metadata 与当前 checkpoint pointer。
- MySQL `runtime_thread_events`：append-only 边界历史。
- Redis `AsyncRedisSaver`：LangGraph checkpoint body。
- 默认 checkpoint TTL：10080 分钟。
- 最大 checkpoint payload：1 MiB。
- checkpoint namespace：`countyflow`。

### 10.2 推进协议

`CheckpointedGraphRunner` 以 `durability="sync"` 流式执行，并在每个节点边界用 expected current checkpoint、state version 与 next node 推进 MySQL pointer。恢复从最新稳定 checkpoint 后的 N+1 节点继续，且通过 ancestry、节点与数量检查阻止重复推进。

### 10.3 版本控制

`runtime_threads` 使用 SQLAlchemy `version_id_col`。并发更新不是 Python 内存等值判断；数据库检测到 stale write 后转换为明确冲突。

### 10.4 历史恢复证据

- Checkpoint 恢复 5/5 成功。
- 从 `intake` checkpoint 恢复后第一个执行节点为 `entity_memory`。
- 单独 checkpoint 证据中的恢复最大值 4.579 秒。
- Worker recovery 5 次：平均 4.770 秒，最大/P95 4.824 秒，最小 4.678 秒。

## 11. Runtime Override

### 11.1 当前允许范围

- 只允许覆盖 `Vehicle.status`。
- 允许 `NORMAL → BROKEN | UNAVAILABLE | MAINTENANCE`。
- 只允许在稳定边界 `environment → capacity`。
- 调用者需要 `runtime:override` 权限。

### 11.2 安全协议

1. 验证 expected state version 与 expected next node。
2. 获取 per-thread Redis lock。
3. 写入 MySQL idempotency ledger。
4. 以 CAS 将线程认领为 `OVERRIDING`。
5. 读取 exact canonical checkpoint。
6. 调用 LangGraph `aupdate_state(..., as_node="environment")`，只 patch `vehicle_status`。
7. 验证生成的是合法 child checkpoint、祖先正确且其他字段未改变。
8. 原子提升 MySQL checkpoint pointer。
9. 写入 intervention event 与 attempt 证据。
10. 若跨存储中断形成 `PARTIAL`，由 reconciler 恢复。

### 11.3 为什么不能直接 UPDATE 数据库

下游 Agent 读取的是 checkpoint state。只更新 MySQL 业务列会造成数据库、LangGraph checkpoint 和审计历史三方分叉，并可与 Worker 节点推进竞态。安全覆盖必须生成新的 child checkpoint 并以 CAS 提升 canonical pointer。

### 11.4 历史并发证据

- 合法覆盖 50/50。
- stale 请求阻断 20/20，silent overwrite 0。
- 并发 20 轮，每轮唯一 winner，违规 0。
- boundary race 50 轮，违规 0。
- Capacity 读取 `BROKEN` 50/50。
- 总体 P95 181.643 ms。

## 12. Shared Memory

### 12.1 Canonical 与投影

- MySQL 是共享事实 canonical control plane。
- Qdrant 和 Neo4j 是投影。
- MySQL 记录 mutation、fact、evidence、attempt 与版本。

### 12.2 决策与状态

决策：`CREATE`、`MERGE`、`REPLACE`、`REJECT`、`CONFLICT_REVIEW`、`NOOP`。

Fact 状态：`ACTIVE`、`EXPIRED`、`PENDING_REVIEW`、`CONFLICT`。

Mutation 状态：`PENDING`、`APPLYING`、`FINALIZING`、`APPLIED`、`PARTIAL`、`REJECTED`、`CONFLICT`、`FAILED`。

Projection 状态：`NOT_REQUIRED`、`PENDING`、`STAGED`、`ACTIVE`、`RETIRED`、`FAILED`。

准确的状态口径：Qdrant/Neo4j 投影是 `STAGED → ACTIVE → RETIRED`；mutation 在投影 staged 后进入 `FINALIZING`，随后 canonical fact 与新投影激活、旧投影退役。不能把 `FINALIZING` 当作 projection 状态。

### 12.3 一致性机制

- Redis fact lock。
- expected version 与 SQLAlchemy `version_id_col`。
- idempotency key。
- 先 stage 投影，再 finalize canonical，再 activate 新投影并 retire 旧投影。
- 失败可进入 `PARTIAL`，由 resume/reconciler 补偿。
- 读取侧只接受 ACTIVE 且未过期的投影，避免 staged 泄漏。

### 12.4 历史证据

- 决策矩阵覆盖 CREATE/MERGE/REPLACE/NOOP/REJECT/CONFLICT。
- Qdrant 与 Neo4j 注入失败均能从 PARTIAL 恢复到 APPLIED。
- staged projection 泄漏：Qdrant 0、Neo4j 0。
- 20 轮并发写 lost update：0。

## 13. Qdrant Vector Memory

- 运行集合名：`entity_resolution_memory`。
- Benchmark 集合名：`entity_resolution_memory_benchmark`。
- 距离：Cosine。
- point id：UUID5，命名输入 `countyflow-memory:{memory_id}`。
- payload：memory_id、driver_id、route_id、anomaly_type、resolution_text、metadata、created_at，可含 data_provenance。
- 搜索过滤：projection_status 为 ACTIVE 或兼容旧数据缺失；expires_at 在未来或兼容旧数据缺失。
- Entity Memory 默认返回 top 3。
- Docker-dev 维度为配置值 128；fake provider 类默认值为 8，但 runtime 显式使用配置维度。

### 13.1 真实 embedding 历史证据

- 日期：2026-08-27。
- API：OpenAI-Compatible，主机 `api.siliconflow.cn`。
- 模型：`Qwen/Qwen3-Embedding-4B`。
- 维度：2560。
- 记忆点：10；查询集：50。
- Top-1：49/50 = 98%。
- Top-3：50/50 = 100%。
- 失败查询：1 个（query 45）。
- 合法采纳：4/4；非法采纳：0/3。
- 本轮未调用外部 embedding API，故这是 HISTORICAL VERIFIED。

## 14. Neo4j Graph Memory

### 14.1 Schema

实体类型 11 个：Driver、Vehicle、Route、Weather、RoadCondition、Station、Anomaly、Resolution、DispatchOrder、PolicyRule、UserPreference。

关系类型 10 个：DRIVES、SERVES、HAS_RISK_ON、AFFECTED_BY、HIGH_RISK_WHEN、ALTERNATIVE_TO、RESOLVED_BY、CONFLICTS_WITH、DEPENDS_ON、STATUS。

- 唯一约束：`GraphEntity.entity_key`。
- 索引：`entity_id`、`entity_type`。
- 查询跳数：1–3，默认 2。
- 默认 limit：25。
- 查询 timeout：1 秒。
- 读取过滤 ACTIVE/兼容旧数据且未过期。
- Docker image：Neo4j 5.26-community。

### 14.2 历史证据

- 基准数据覆盖 8 个实体类型、6 个关系类型；这不等于代码 schema 上限。
- fact recall：20/20。
- path recall：20/20。
- warm 50 样本：平均 7.808 ms，P95 10.354 ms，最大 12.632 ms。

## 15. MySQL 持久化与迁移

MySQL canonical 表覆盖：orders、anomalies、dispatches、audit_records、dispatch_tasks、runtime_threads、runtime_thread_events、runtime_overrides、runtime_override_attempts、memory_mutations、memory_facts、memory_evidence、memory_mutation_attempts、security_audit_events、demo_employee_accounts、dispatch_publications。

Alembic 共 10 个 migration，最新为 `20260830_10_delivery_employee_role.py`。

使用 SQLAlchemy optimistic locking 的关键实体：Dispatch、RuntimeThread、MemoryFact。`StaleDataError` 被转为业务冲突/HTTP 409，而非静默覆盖。

距离与成本等精度敏感值使用 `Decimal`。

## 16. API 能力地图

### 16.1 身份与会话

- demo employees
- demo session
- development session
- current principal (`me`)
- logout/revocation

### 16.2 工作区读取

- workspace overview
- orders
- anomalies
- reviews
- my tasks
- runtime threads
- memory records

### 16.3 调度与人工操作

- create/status/result dispatch task
- publish dispatch result
- review decision
- runtime thread by task/detail/history
- runtime override create/detail/history
- memory mutation create/get/fact

### 16.4 运维与安全

- observability summary/agents/workers/memory/runtime/dependencies，共 6 类读取入口
- security audit
- websocket ticket
- task event WebSocket
- health

## 17. 身份、权限与安全

### 17.1 Principal

`AuthenticatedPrincipal` 包含 subject、display_name、roles、permissions、auth_method、issued_at、expires_at、jti。

### 17.2 实际角色数

当前真实角色是 6 个，不是 5 个：

1. EMPLOYEE
2. DISPATCHER
3. SUPERVISOR
4. OPERATOR
5. AUDITOR
6. ADMIN

可以表述为“五个管理/专业角色 + 一个一线配送员工角色”。

### 17.3 角色能力摘要

| 角色 | 主要权限 |
|---|---|
| EMPLOYEE | `dispatch:read`，查看本人任务 |
| DISPATCHER | 调度读写、订单/异常/Agent/记忆读取 |
| SUPERVISOR | Dispatcher 能力 + review、memory mutate、runtime override、audit、monitor |
| OPERATOR | Agent、runtime、audit、monitor |
| AUDITOR | memory、runtime、audit、monitor 读取 |
| ADMIN | 全部权限 |

权限全集包括 dispatch:read/create/review、orders:read、anomalies:read、agents:read、memory:read/mutate、runtime:read/override、audit:read、monitor:read、system:admin。

### 17.4 JWT/OIDC

- Development JWT：HS256，secret 最短 32 字符。
- OIDC boundary：RS256/ES256 allowlist，JWKS resolver/cache/timeout。
- 校验 issuer、audience、iat、nbf、exp、jti。
- Redis 保存 token revocation。
- production profile 要求 OIDC/JWKS、HTTPS CORS，禁止 dev/fake provider。

### 17.5 Rate Limit

Redis token bucket 按 subject 与 operation class 限流。高风险写操作在 Redis 不可用时 fail closed；低风险读有小型本地 emergency limiter。

默认配额：submit 30/120 min、override 3/12 min、memory 5/30 min、observability 60/300 min、WS ticket 10/60 min、invalid auth 10/60 min。

### 17.6 WebSocket Ticket

- 随机 ticket，Redis 仅存 digest。
- TTL 45 秒。
- `GETDEL` 单次消费。
- 严格绑定 task scope 与 permission。
- wrong scope 关闭码 4403。
- replay/expired 关闭码 4408。
- missing ticket 关闭码 4401。
- 安全控制面不可用关闭码 1011。
- 握手后先发 task snapshot，再补历史 event，再订阅 live event。

### 17.7 防护与脱敏

- CSP、nosniff、Referrer-Policy、Permissions-Policy。
- production 可启用 HSTS。
- JSON body size limit。
- CORS allowlist。
- redactor 覆盖 Bearer、Basic、JWT、带凭证 URL、query secret 与敏感 key。
- Security audit 记录 durable event。

## 18. Frontend 当前事实

### 18.1 技术栈与样式

- React 19.2.8。
- React Router DOM 7.18.2。
- Vite 8.2.2。
- TypeScript 6.0.3。
- Vitest 4.1.11。
- Playwright 1.62.1。
- 当前最终 CSS 是白色 App Shell、teal accent、响应式布局。
- 样式文件中仍有早期 dark rules，但在后续规则中被完整覆盖；浏览器历史验收的 computed style 为白色。
- 支持 keyboard focus、reduced motion、可访问表格/对话框/tab/graph node。

### 18.2 路由

`/workspace`、`/supervisor`、`/operations`、`/audit`、`/overview`、`/my-tasks`、`/team-tasks`、`/reviews`、`/runtime`、`/dispatch`、`/dispatch/:taskId`、`/anomalies`、`/orders`、`/agents`、`/memory`、`/monitor`。

`/team-tasks` 当前故意显示 NOT_EXPOSED，不应描述为已交付团队任务页。

### 18.3 真实与未暴露数据

- Admin overview：真实 workspace overview counts。
- Orders/Anomalies：真实分页 API，明确 EMPTY/UNAVAILABLE。
- Reviews：真实队列与人工决策。
- My Tasks：真实员工本人任务。
- Runtime：真实线程元数据，不返回完整 checkpoint body。
- Memory：真实 Qdrant read model。
- Supervisor：真实 review summary + runtime summary；全局 intervention history 未暴露。
- Dispatcher：真实任务按 pending/running/completed 分区；工作区级 AI 推荐聚合未暴露。
- Operator：真实 observability + runtime summary。
- Auditor：真实 security audit；全局业务、记忆、override 历史未暴露。
- API mode 不会在失败时静默回退到 mock data。

### 18.4 UI 数据真值状态

`LIVE`、`DEMO`、`VERIFIED`、`STALE`、`NOT_EXPOSED`、`UNAVAILABLE`、`NO_PERMISSION`，另含 `EMPTY`。

## 19. Docker 与启动方式

### 19.1 Compose 声明拓扑

11 个 service：mysql、neo4j、qdrant、redis、migration、worker-1、backend、prometheus、worker-2、frontend、grafana。

- 长期运行 service：10 个；migration 是一次性任务。
- Named volume：6 个，分别用于 MySQL、Redis、Qdrant、Neo4j、Prometheus、Grafana。
- Network：default 与 host_access。
- 镜像：MySQL 8.4、Neo4j 5.26-community、Redis 8.2.9-alpine、Prometheus 3.5.0、Grafana 12.1.0，以及自建 backend/worker/migration/frontend/Qdrant 配置。
- Healthcheck：backend、mysql、neo4j、prometheus、qdrant、redis、grafana。
- 无 healthcheck：frontend、migration、worker-1、worker-2。
- Worker restart policy：unless-stopped。

### 19.2 本轮状态

- `docker compose --env-file .docker.env config --services` 成功。
- `docker compose ps` 因 Docker daemon 未运行而失败。
- 所以拓扑配置 VERIFIED，当前在线容器数 NOT VERIFIED。
- 历史证据记录 10 个长期容器运行、migration exit 0。

### 19.3 两种启动模式

- Light launcher：SQLite + backend/frontend，不含 Redis/Worker，不代表生产异步链路。
- Full launcher：Docker 构建并启动 11 个 compose service，代表完整开发验收拓扑。

## 20. Observability

### 20.1 当前代码/规则数量

- MetricDefinition family：46。
- Prometheus recording rule：9。
- Prometheus alert rule：18。

旧 G1 文档中的 42 metrics / 13 alerts 已被后续安全指标与告警扩展超越，不得继续作为当前数字。

### 20.2 Recording Rules

http_qps、http_p95、http_error_ratio、agent_p95、graph_p95、checkpoint_p95、override_success_ratio、worker_pending、stream_lag。

### 20.3 Alerts

CountyFlowBackendDown、CountyFlowWorkerDown、CountyFlowDependencyDown、CountyFlowApiLatencyHigh、CountyFlowApiErrorRateHigh、CountyFlowGraphLatencyHigh、CountyFlowWorkerRecoverySloBreach、CountyFlowInvariantViolation、CountyFlowWorkerPendingBacklog、CountyFlowWorkerStreamLagHigh、CountyFlowCheckpointLatencyHigh、CountyFlowMemoryPartialStuck、CountyFlowOverrideConflictSpike、AuthenticationFailureSpike、AuthorizationDeniedSpike、RuntimeOverrideDeniedSpike、RateLimitSpike、WsTicketRejectionSpike。

### 20.4 SLO

- API P95 < 300 ms，rolling 5 min，至少 100 请求。
- 5xx error ratio < 0.1%，rolling 5 min，至少 100 请求。
- Graph P95 < 150 ms，至少 20 次查询。
- Worker recovery ≤ 5 s。
- projection leak = 0。
- downstream stale read = 0。

Checkpoint 与其他门槛属于 guardrail，不应全部称作 SLO。

### 20.5 历史故障隔离

- Neo4j dependency alert 经 pending → firing（2 min）→ resolved。
- Neo4j down 可见且业务走降级。
- worker-1 down 时 worker-2 继续。
- Prometheus 不可用时业务保持健康。
- Grafana 故障与业务隔离。

## 21. 测试与本轮验证

### 21.1 Backend

- 测试文件：168。
- Ruff：通过；有两个不可访问历史临时目录告警。
- 默认环境 pytest：收集阶段 15 errors，根因是被忽略 `.env` 中 dev JWT secret 太短。
- 隔离认证 Provider 后：850 passed、7 skipped、768 warnings，耗时 224.62 s。
- 7 skipped：2 个真实 Redis checkpoint、1 个真实 security MySQL、3 个真实 security Redis、1 个真实 shared-memory race。
- 这些 skip 本轮因所需 Docker / MySQL / Redis 环境与安全配置不可用而未补跑。

### 21.2 Frontend

- Vitest：52 files、238 tests passed。
- ESLint：exit 0，0 error，2 个 Fast Refresh warning。
- Build：成功，1917 modules transformed。
- 产物：CSS 73.75 kB（gzip 14.51）；主 JS 498.35 kB（gzip 146.47）。
- Playwright spec：15 个。
- 司机上报 Playwright spec 在真实本地 Docker 栈与 `http://localhost:5173` 上为 1/1 passed；覆盖员工登录、本人任务、跨员工 403、异常提交 202、真实 anomaly/task identity 与 390px 无横向溢出。

### 21.3 已知警告债务

- 测试有较多 deprecation/runtime warnings，主要包括 FastAPI `on_event` 等兼容提醒。
- Qdrant client/server version probing 在部分测试上下文产生提醒。
- 两个 ACL 异常临时目录影响扫描整洁度。
- Frontend 两个 Fast Refresh warning 不阻断 lint/build。

### 21.4 2026-09-01 司机异常上报增量

- `EMPLOYEE` 新增 `anomalies:report` 权限；司机只能从本人 READY / WAITING / ACTIVE 配送任务上报问题。
- `POST /api/v1/anomaly-reports` 会从服务端任务推导订单、司机、车辆与路线，持久化异常后复用既有异步调度提交链路。
- 上报幂等键同时约束异常与调度任务；同键同内容安全重放，同键不同内容（含并发争用）返回冲突且不重复调度。
- 前端新增 `/report-issue`，My Tasks 增加“提出问题/报告问题”入口；`/dispatch` 改为任务中心，不再提交固定演示案例。
- 本地 mock 页面已在 1440px 与 390px 视口执行结构、交互、控制台和横向溢出检查，均通过；该检查不等同于真实 Docker 全链路 E2E。
- 使用现有 `.docker.env` 重建后，司机异常上报真实依赖 Playwright 用例为 1/1 passed；这不等同于全部历史 Playwright、故障注入或性能门禁均已重跑。
## 22. 历史集成、并发与性能证据

### 22.1 V2-E 黑盒

- 15 轮：15/15 PASS。
- pending：0。
- duplicate audit/dispatch：0。
- shared/vector/graph persistence、override state、downstream broken checks：均为 true。

### 22.2 Dispatch 并发

- 20/20 冲突被拦截。
- silent overwrite：0。

### 22.3 V2-E Locust

- 3 × 60 秒，50 users。
- 混合 health/status/result/threads/history/override/Qdrant/Neo4j/shared mutation。
- 最低 QPS：400.071。
- 最大 P95：200 ms。
- 最大 graph P95：9 ms。
- error：0。

### 22.4 Security ON

- 日期：2026-08-29。
- 请求：16,575。
- 50 users，60 s。
- QPS：278.998。
- P95：270 ms。
- unexpected error：0。

### 22.5 Observability ON 最新原始证据

- 日期：2026-08-29。
- API 请求：3,000；concurrency 64。
- API P95：66.022 ms。
- QPS：1037.85。
- error：0。
- graph workflow P95：167.311 ms。
- override P95：158.597 ms。
- worker throughput：0.479/s。

注意：graph workflow P95 167.311 ms 高于定义的 150 ms SLO；该条证据不能被包装为 graph SLO PASS。旧汇总与最新 raw JSON 存在运行批次差异时，以 raw JSON 及日期为准。

## 23. Secret Safety

- `.env` 与 `.docker.env` 均被 Git ignore。
- `.env.example` 仅保留空值/示例结构。
- 历史 value-based scan：838 个仓库文件，对 6 个已配置 secret value，0 findings。
- V2-F `final-gates.json` 的 `secret_scan_findings` 为 0。
- 本轮没有读取、输出或重新扫描真实 secret value，因此当前状态是 HISTORICAL VERIFIED，而非本轮 live re-verification。

## 24. 灾备与业务连续性

当前未发现以下实现或证据：

- MySQL/Qdrant/Neo4j/Redis 自动备份脚本。
- 一致性 backup manifest。
- checksum 校验。
- secret sanitizer。
- restore 脚本。
- RPO/RTO 自动测量。
- DR drill 测试与原始报告。
- V2-G3 验收目录。

因此灾备状态为 DEFERRED / NOT IMPLEMENTED。测试中的 runtime snapshot 变量指状态快照，不是存储备份，不得混淆。

## 25. 版本演进事实

| 阶段 | 已落地重点 |
|---|---|
| V1 | 异步任务、Redis Streams、8-Agent 图、基础持久化与 UI |
| V2-A | Neo4j Graph Memory |
| V2-B | Shared Memory canonical control plane 与双投影 |
| V2-C | Checkpoint / Runtime Thread |
| V2-D1 | Runtime Override |
| V2-D2 | Intervention Workbench |
| V2-E | 综合验收、性能、竞态、恢复 |
| V2-F | Frontend productization |
| V2-G1 | Observability |
| V2-G2 | Security hardening |
| V2-F2 | Role-based white UI |
| 2026-08-29 后续 | 真实 workspace read models、完整 runtime build context |
| 2026-08-30 后续 | demo employee、My Tasks、manual review、dispatch publication、delivery employee role |
| V2-G3 | 无实现证据，DEFERRED |

## 26. 当前工具与依赖版本

### 26.1 Backend

- Python 3.12.7；项目要求 ≥3.12。
- FastAPI 0.141.1。
- LangGraph 1.2.11。
- langgraph-checkpoint-redis 0.5.2。
- SQLAlchemy 2.0.52。
- Alembic 1.19.1。
- redis-py 6.4.0。
- qdrant-client 1.19.0。
- neo4j 6.2.0。
- prometheus-client 0.26.0。
- PyJWT 2.13.0。
- httpx 0.28.1。

### 26.2 Frontend

- Node 24.18.0。
- npm 11.16.0。
- React / ReactDOM 19.2.8。
- React Router DOM 7.18.2。
- Vite 8.2.2。
- TypeScript 6.0.3。
- Vitest 4.1.11。
- ESLint 10.8.1。
- Playwright 1.62.1。
- lucide-react 1.33.0。

## 27. 不能声称的事项

1. 不能声称当前图由 LLM 生成调度结论。
2. 不能声称 Docker runtime 使用真实 embedding。
3. 不能声称 Capacity/Route 已接生产系统。
4. 不能声称 production runtime wiring 完成。
5. 不能声称 exactly-once delivery。
6. 不能声称灾备、备份恢复与 RPO/RTO 已完成。
7. 不能声称全部 Docker 专项集成、全部 Playwright、故障注入或 Locust 已重新执行；本轮只重新验证了当前容器健康与司机异常上报 E2E 1/1。
8. 不能声称当前只有 5 个角色。
9. 不能声称 `/team-tasks` 已交付。
10. 不能声称所有 Auditor 全局审计视图已暴露。
11. 不能把历史性能证据冒充 2026-08-31 在线数据。
12. 不能声称默认 `make test` 在当前本地 `.env` 下通过。

## 28. 最终工程判断

### 28.1 已完成程度

异步任务、可恢复执行、人工覆盖、双形态记忆、并发控制、角色权限、安全审计、白色多角色 UI、Prometheus/Grafana 配置与大量自动化测试已经形成相互闭环。工程原型完整度高，尤其在状态一致性与证据留存方面明显超出一般演示项目。

### 28.2 生产就绪差距

生产前至少需要：

1. 实现并验收 production Provider wiring，包括真实 Capacity、Routing、Embedding 以及是否实际启用 LLM 的明确设计。
2. 建立 V2-G3：跨存储备份、manifest、checksum、sanitizer、恢复、RPO/RTO 与演练。
3. 在干净 CI 环境和可用 Docker daemon 上重跑所有真实依赖 integration、Playwright、故障注入与性能门禁。
4. 修复本地 dev JWT 配置漂移，保证默认质量门禁不依赖临时环境覆盖。
5. 处理测试 warnings、ACL 临时目录与前端 Fast Refresh warnings。
6. 为 Worker/frontend 增补可操作的 readiness/health 与部署编排策略。
7. 明确尚未暴露的 Supervisor/Auditor/Team Tasks 产品范围。

### 28.3 最终状态

当前可判定为：`工程化智能调度原型已完成，生产化与灾备未完成`。
