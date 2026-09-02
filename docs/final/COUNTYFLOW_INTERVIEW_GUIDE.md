# CountyFlow 面试讲解与项目复盘指南

> 事实源：[FINAL_FACTS.md](./FINAL_FACTS.md)
> 使用原则：只讲当前实现与可追溯证据；历史性能必须带测试阶段，不把开发拓扑包装成生产部署。

## 1. 3 分钟项目介绍

CountyFlow 是一个县域物流异常识别与智能调度系统。它解决的不是单次“问 AI 应该走哪条路”，而是把订单异常、司机车辆状态、天气道路、历史经验、人工复核和最终调度组织成一条可恢复、可审计的异步业务链路。

前端提交任务后，FastAPI 完成认证、RBAC、限流、任务持久化和 Redis Streams 发布，两个 Worker 通过 consumer group 消费。Worker 为任务建立 Runtime Thread，执行固定顺序的 8-Agent LangGraph：Intake、Entity Memory、Graph Memory、Environment、Capacity、Routing、Dispatch、Audit。Qdrant 负责相似经验，Neo4j 负责实体关系与多跳路径，MySQL 是业务与共享记忆控制面的 canonical truth。

项目最有技术含量的是运行时一致性。LangGraph checkpoint body 保存在 Redis，而 MySQL Runtime Registry 保存 current checkpoint pointer 和 state version。Worker 崩溃后从 N+1 节点恢复。若 AI 执行时人工发现车辆故障，Supervisor 可在 `environment → capacity` 稳定边界执行 Runtime Override：通过 Redis lock、MySQL CAS、`aupdate_state` 与 checkpoint promotion，把 `NORMAL` 安全改成 `BROKEN`，让后续 Capacity Agent 读取新状态；绝不是旁路 UPDATE DB。

可靠性上，系统结合 terminal-state-before-ACK、XAUTOCLAIM、有界重试、DLQ、Redis execution lock、MySQL idempotency ledger 和 SQLAlchemy optimistic locking，实现 effectively-once business effect。安全上有 JWT/OIDC boundary、六角色 RBAC、Redis token bucket、durable security audit、敏感数据脱敏与 45 秒 single-use WebSocket ticket。

当前本轮测试结果是后端 833 passed、7 skipped，前端 228 passed，lint 与 build 通过。历史综合验收包含 15/15 黑盒、消息丢失 0、stale override 全部阻断、Shared Memory lost update 0。项目已达到高完整度工程原型，但不能称为生产完成：Docker runtime 仍是 fake embedding 和 in-memory capacity/routing，生产 Provider wiring 与 V2-G3 灾备未实现。

## 2. 10 分钟详细讲解

### 第 1 分钟：业务背景

县域物流异常通常横跨订单、司机、车辆、路线、天气、道路与站点容量。信息来源碎片化，状态变化快，单一同步接口很容易超时，也无法在 Worker 崩溃或人工介入后恢复。CountyFlow 的目标是让一次智能调度成为耐久业务流程。

### 第 2 分钟：异步架构

FastAPI 只创建任务并 `XADD`，不在请求线程跑 Agent。Redis Streams 提供 consumer group、pending list 与 `XAUTOCLAIM`；两个 Worker 提供并行度和单 Worker 故障接管。MySQL 保存长期任务真相，Redis 不承担长期 source of truth。

### 第 3 分钟：8-Agent

图按 Intake → Entity Memory → Graph Memory → Environment → Capacity → Routing → Dispatch → Audit 执行。节点单一职责、依赖由窄接口注入。记忆和外部环境失败可降级；Dispatch 并发冲突与 Audit 持久化失败不能静默吞掉。

### 第 4 分钟：Memory

Qdrant 用 Cosine vector search 找语义相似的历史处置；Neo4j 查 Driver、Vehicle、Route、Weather 等实体的明确关系与多跳路径；MySQL Shared Memory Control Plane 管理 canonical fact、evidence、mutation、version 和 projection lifecycle。Vector 解决“像不像”，Graph 解决“有什么关系”，Shared Memory 解决“哪条才是真相”。

### 第 5 分钟：Runtime Thread

普通 checkpoint 只存图状态，不足以提供业务级 canonical pointer 和并发版本。项目增加 MySQL registry 与 append-only event，Redis 保存 checkpoint body。每个节点边界使用 expected checkpoint、state version 与 next node CAS 推进；重启时验证 ancestry，从 N+1 恢复。

### 第 6 分钟：Runtime Override

Supervisor 在稳定边界把车辆 NORMAL 改为 BROKEN。服务先验权限和限流，再拿 per-thread Redis lock，以 MySQL CAS 认领 OVERRIDING，读取 exact checkpoint，调用 `aupdate_state(as_node="environment")` 生成 child checkpoint，验证只改目标字段，最后提升 pointer。Worker 恢复到 Capacity，读到 BROKEN 并将车辆视为 unavailable。

### 第 7 分钟：并发与幂等

Redis lock 是快速互斥，MySQL optimistic locking/CAS 是最终一致性屏障，idempotency key 是请求重放边界。Stream 只在耐久终态后 ACK；重复 delivery 命中 terminal ledger。Shared Memory 先 stage projection、再 finalize canonical、activate 新投影、retire 旧投影；PARTIAL 由 reconciler 补偿。

### 第 8 分钟：安全与 WebSocket

Development JWT 与 production OIDC/JWKS boundary 共用 `AuthenticatedPrincipal`。实际有六角色。高风险写使用 Redis token bucket，控制面失效时 fail closed。WebSocket 不直接复用长生命周期 bearer query，而用 45 秒、single-use、task-scoped ticket；Redis 只保存 digest。

### 第 9 分钟：Frontend 与 Observability

React UI 是白色企业级 App Shell，角色工作区根据真实权限和 read model 展示。LIVE、DEMO、STALE、NOT_EXPOSED、UNAVAILABLE、NO_PERMISSION 被显式区分，API mode 不回退 mock。可观测性有 46 metrics、9 recording rules、18 alerts，覆盖 API、Worker、Agent、Memory、Checkpoint、Override、Security 与依赖。

### 第 10 分钟：结果与边界

本轮后端 833 pass、前端 228 pass；历史 15-round 15/15、V2-E error 0、worker recovery 最大 4.824 秒。真实 embedding 历史 Top-1 98%、Top-3 100%。必须同时说明：这些性能没有在本轮 Docker daemon 关闭的条件下重跑；当前 compose 是 docker-dev，生产 Provider 和灾备未实现。

## 3. 30 分钟技术深挖提纲

### 0–5 分钟：领域与边界

1. 解释县域物流异常的时效性、多实体、多依赖特征。
2. 展示为什么同步 Agent endpoint 不适合长流程。
3. 明确 MySQL、Redis、Qdrant、Neo4j 的真相边界。

### 5–10 分钟：执行状态机

1. 展开 GraphState 与 8 个节点。
2. 说明 checkpoint boundary 与 append-only runtime event。
3. 演示 N+1 resume 和 audit-before-ACK。

### 10–15 分钟：Memory 治理

1. 对比 semantic similarity 与 graph traversal。
2. 展开 CREATE/MERGE/REPLACE/CONFLICT/NOOP。
3. 解释 projection STAGED、mutation FINALIZING、projection ACTIVE/RETIRED。
4. 说明 PARTIAL crash recovery 和 staged leak 防护。

### 15–20 分钟：人工干预与竞态

1. 讲车辆运行中故障场景。
2. 展开 Redis lock、expected version、MySQL CAS、`aupdate_state`。
3. 解释 Worker wins 与 Override wins 两种合法结果。
4. 给出 stale 20/20、并发 winner 20/20、boundary race 50/50 的历史证据。

### 20–25 分钟：安全与可观测性

1. 从 token 到 Principal，再到 permission 与 rate bucket。
2. 展开 WS ticket 的 digest、TTL、GETDEL 与 scope。
3. 解释业务 Audit 和 Security Audit 的差别。
4. 解释 Prometheus cardinality 与 normal/pending/firing/resolved。

### 25–30 分钟：验证与生产差距

1. 区分 unit、integration、browser、failure injection、race 与 Locust。
2. 解释本轮 833/7 与默认 `.env` 配置漂移。
3. 区分 V2-E、Security ON、Observability ON 性能批次。
4. 主动指出 production Provider、DR、全量当前重验与部分 UI exposure 缺口。

## 4. Top Technical Highlights

### 4.1 Runtime State Override

亮点不在“提供修改状态接口”，而在把人工修改变成合法 child checkpoint，并用 ancestry、字段差异、CAS 和事件审计证明修改没有旁路破坏图状态。

### 4.2 Persistent Runtime Thread

将 LangGraph checkpoint 从内部实现细节提升为业务可管理 Runtime Thread：MySQL 管 pointer/version/history，Redis 管 checkpoint body，Worker 可以在崩溃后从 N+1 恢复。

### 4.3 Effectively-Once Worker

不是依赖单一中间件承诺，而是组合 consumer group、pending recovery、execution lock、idempotency ledger、optimistic lock 和 terminal-before-ACK，控制最终业务副作用。

### 4.4 Graph + Vector + Shared Memory

三层解决三个问题：开放语义召回、已知关系推理、canonical fact 与跨存储写治理。Shared Memory 使 Qdrant/Neo4j 从孤立数据库变成可恢复投影。

### 4.5 Data Truth Frontend

前端不把“接口失败”伪装成“演示成功”，而是显式展示 LIVE、DEMO、STALE、NOT_EXPOSED、UNAVAILABLE 和 NO_PERMISSION，减少运营误判。

### 4.6 Security 与实时链路闭环

REST 与 WebSocket 都以 Principal/permission 为核心；WS 使用短期单次 ticket，避免在 query 中长期暴露 bearer token。安全拒绝本身进入 durable audit 与 metrics。

## 5. 真正的技术难点

| 难点 | 为什么难 | 当前方案 | 结果 |
|---|---|---|---|
| 多 Agent 状态管理 | 节点多、字段多、失败语义不同 | Typed GraphState + 固定节点顺序 + narrow dependencies | 8 节点行为可独立测试 |
| Checkpoint canonical pointer | Redis 有状态体但不等于业务当前版本 | MySQL registry + Redis checkpointer | 可验证 N+1 resume |
| Worker crash | 消息可能 pending、节点可能已提交 | terminal-before-ACK + XAUTOCLAIM + checkpoint | 历史恢复 ≤4.824s |
| 双 Worker 同任务 | delivery 可能重复且并行 | Redis execution lock + MySQL ledger | duplicate side effect 0 historical |
| Runtime Override | 人工修改与 Worker 节点推进竞态 | stable boundary + lock + CAS + aupdate_state | 历史竞态违规 0 |
| Shared Memory 跨存储 | MySQL/Qdrant/Neo4j 无分布式事务 | staged projections + finalization + reconciler | projection leak 0 historical |
| Shared Memory 并发 | 相同 fact 可能同时更新 | fact lock + expected version + version_id_col | lost update 0/20 historical |
| Vector/Graph 协同 | 相似与关系容易被混为一谈 | 两套 repository、不同 evidence semantics | recall 分工清晰 |
| Provider failure | 外部服务不可控且可能泄密 | async timeout、normalized errors、circuit breaker | Environment 可快速 fallback |
| WebSocket 鉴权 | 长连接重放与 scope 风险 | digest-only single-use ticket + GETDEL | 45s、task scoped |
| Metrics cardinality | task/user id 会炸 label 基数 | stable enum labels，ID 放日志/审计 | 46 family 可运营 |
| 多角色前端 | 同一能力对不同角色可见/可写不同 | permission-aware routes/actions/truth states | 六角色 UX |
| 测试环境漂移 | 本地 `.env` 可影响收集期配置 | 本轮进程级隔离定位根因 | 833 pass，默认入口仍需修复 |
| Windows 临时目录 ACL | 扫描和测试清理受拒绝 | 避免破坏性删除，记录告警 | 不掩盖当前门禁状态 |
| 灾备 | 多存储恢复顺序与一致性复杂 | 当前没有实现 | 明确 DEFERRED，不伪造完成 |

## 6. 高频高级面试问答

### Q1：为什么设计成多 Agent，而不是单 Agent？

单 Agent 会把输入校验、记忆、环境、运力、路线、持久化和审计混成不可观测的黑盒。8 个节点让每一步输入输出、超时、降级、指标和测试可独立定义。代价是状态与恢复更复杂，所以项目配套 Runtime Thread 和 checkpoint protocol。

### Q2：为什么不用一个大模型 Prompt 完成全部决策？

当前系统甚至没有在 8-Agent graph 中调用 LLM，这是有意保持确定性边界。运力、并发写、审计和权限不应该交给自由文本推理。LLM abstraction 已存在，未来可在明确节点做受控增强，但不能替代事务与状态机。

### Q3：为什么选择 LangGraph？

它提供显式图、typed state、节点边界与 checkpointer 协议，适合长流程恢复和人工更新状态。项目又在其上增加 MySQL Runtime Registry，弥补业务级 current pointer、版本和审计需求。

### Q4：为什么使用 Redis Streams？

它与现有 Redis 锁、checkpoint、安全控制栈协同，提供 consumer group、pending entry、XAUTOCLAIM 和有序 stream id，适合当前规模的异步任务。项目需要的是可恢复工作队列，而非复杂事件平台。

### Q5：为什么不用 Kafka？

Kafka 在高吞吐、多订阅者、长期事件保留与跨团队事件平台上更强，但运维复杂度更高。当前 CountyFlow 是任务消费模式，Redis Streams 足够且降低基础设施成本。若未来吞吐、分区扩展或事件重放需求显著增长，再评估 Kafka。

### Q6：为什么使用 MySQL？

订单、任务、调度、审计、版本与权限事件需要事务、唯一约束、行版本和稳定查询。MySQL 是 canonical truth，避免 Redis、Qdrant、Neo4j 各自成为冲突真相。

### Q7：为什么选择 Qdrant？

它提供明确的 vector collection、Cosine 距离、payload filter 和 top-k query，适合按异常文本召回相似处置经验。真实 embedding 历史 benchmark 的 Top-1 为 98%、Top-3 为 100%。

### Q8：为什么还需要 Neo4j？

“文本相似”不能证明 Driver DRIVES Vehicle 或 Route AFFECTED_BY Weather。Neo4j 保存明确实体关系，支持 bounded multi-hop path 和 known facts，适合解释关系链。

### Q9：Vector 与 Graph 的本质区别是什么？

Vector 是连续空间中的近似语义相似；Graph 是离散边上的事实连接和路径约束。前者擅长模糊召回，后者擅长可解释关系。两者输出证据类型不同。

### Q10：为什么还要 Shared Memory？

Qdrant 和 Neo4j 都不能独立回答“哪条事实是 canonical、版本是什么、冲突如何处理”。Shared Memory 用 MySQL 管 evidence、mutation、fact、attempt 与 projection lifecycle，解决跨存储写一致性。

### Q11：STAGED、FINALIZING、ACTIVE、RETIRED 如何理解？

STAGED/ACTIVE/RETIRED 是 projection 状态，FINALIZING 是 mutation 状态。先把新投影 stage，mutation 再 finalizing canonical fact，成功后激活新投影并退役旧投影。读取侧只看 ACTIVE，防止半成品泄漏。

### Q12：PARTIAL 怎么恢复？

每次 mutation 有 durable attempt 和已完成步骤。reconciler 读取 canonical mutation/fact 与 projection 状态，幂等地继续未完成阶段；不会盲目回滚已经安全完成的外部写。

### Q13：为什么需要双 Worker？

一是并行处理不同任务，二是单 Worker 崩溃后另一个能 reclaim pending。两个 Worker 也引入同任务竞态，所以必须配 execution lock、idempotency 与数据库版本控制。

### Q14：如何保证幂等？

入口用稳定 idempotency key 解析唯一 task；Worker 先查 MySQL ledger；终态重复 delivery 直接重放；业务写有唯一约束/optimistic lock；Memory mutation 与 Override 也各自有 idempotency record。

### Q15：为什么只能叫 effectively-once？

网络与进程崩溃下消息可能重复 delivery，Redis Streams 不提供端到端 exactly-once。系统通过重放检测和副作用约束保证最终业务效果一次，因此准确名称是 effectively-once business effect。

### Q16：Worker 挂了怎么办？

未 ACK 消息留在 pending。超过 idle threshold 后另一 Worker `XAUTOCLAIM`，读取 MySQL current pointer 与 Redis checkpoint，从 N+1 节点恢复。若终态已存在，直接 ACK 而不重做 dispatch。

### Q17：Checkpoint 丢失怎么办？

MySQL pointer 与 Redis body 必须配对。body 缺失时不能安全猜测 GraphState，系统应进入错误/对账，而不是从头运行并冒险重复副作用。真正 DR 还需要备份恢复，这部分当前未实现。

### Q18：为什么普通 LangGraph checkpoint 不够？

业务还需要 task-thread 映射、current pointer、state version、next node、人工覆盖状态和 append-only audit。MySQL Runtime Registry 承担这些 canonical metadata，checkpointer 只保存状态体。

### Q19：为什么需要 Runtime Override？

长流程执行时现实世界会变化。例如 Environment 完成后发现车辆故障，继续用 NORMAL 决策会产生错误路线。Override 允许授权人在安全边界把新事实写入图状态，让后续节点自然消费。

### Q20：为什么不能直接 UPDATE DB？

Capacity Agent 读取 checkpoint GraphState，不读取旁路数据库字段。直接 UPDATE 会造成 DB、checkpoint 和 audit 分叉，还可能与 Worker 推进竞争。必须用 `aupdate_state` 生成 child checkpoint 并提升 canonical pointer。

### Q21：Worker 与 Override 同时发生怎么办？

二者竞争 MySQL expected pointer/state version CAS。Worker 先赢则 Override stale；Override 先赢则线程进入 OVERRIDING，生成并提升 child checkpoint，Worker 从新状态继续。只有一个合法 winner。

### Q22：Neo4j 挂了怎么办？

Graph Memory Agent 捕获依赖失败，返回空 facts/paths 和错误标记，主流程继续使用其他证据；dependency metric 和 alert 可见。历史故障注入验证了降级和告警生命周期。

### Q23：Qdrant 或 Embedding 挂了怎么办？

Entity Memory 召回降级为空并记录 `MEMORY_RECALL_ERROR`。Shared Memory 写投影失败则 mutation 进入 PARTIAL，读取侧不会看到 STAGED 投影，reconciler 后续恢复。

### Q24：外部天气/道路 API 超时怎么办？

使用显式 async timeout、circuit breaker 和静态路线 fallback。连续失败打开 breaker，避免请求雪崩，并快速返回文档化降级结果。

### Q25：如何防止越权？

后端从 token 构造 `AuthenticatedPrincipal`，每个 endpoint 检查 permission；前端隐藏或禁用操作只是 UX。拒绝事件写 Security Audit，敏感高风险操作另有限流与 fail-closed。

### Q26：WebSocket 怎么鉴权？

先通过受保护 REST endpoint 申请 task-scoped ticket。ticket 45 秒有效、单次使用，Redis 只存 digest，连接时用 GETDEL 消费。scope、重放、过期与控制面失败都有明确关闭语义。

### Q27：为什么前端不是五个角色？

当前代码实际是六个角色。早期是 Dispatcher、Supervisor、Operator、Auditor、Admin 五个专业/管理角色；后续为了 My Tasks 增加 EMPLOYEE。面试时应主动说明演进，而不是重复旧数字。

### Q28：API Mode 为什么禁止 Mock fallback？

静默 fallback 会把服务不可用伪装成业务正常，造成 KPI、列表和操作反馈矛盾。CountyFlow 显式显示 UNAVAILABLE、STALE 或 EMPTY，让用户知道数据真值。

### Q29：如何监控系统？

Prometheus 收集 API、Worker、Agent、Graph、Vector、Memory、Checkpoint、Override、Security 与 dependency metrics；9 条 recording rule 生成稳定查询，18 条 alert rule 管理故障。Grafana 只做可视化，不是业务依赖。

### Q30：如何控制 Prometheus cardinality？

指标 label 只使用 method、route template、status class、agent name、outcome 等稳定枚举。task id、user id、raw error 放日志或审计，而不是 label。

### Q31：当前性能如何描述才准确？

分批次描述：V2-E 混合负载 min QPS 400.071、max P95 200 ms、error 0；Security ON QPS 278.998、P95 270 ms；Observability ON API QPS 1037.85、P95 66.022 ms。不能只选最高 QPS，也不能说这些是本轮实时结果。

### Q32：最新 Observability raw evidence 有什么风险信号？

graph workflow P95 167.311 ms，高于 150 ms Graph SLO。虽然 API P95 很好，也不能把整次运行称为全部 SLO PASS。这体现了按指标逐项判断的重要性。

### Q33：当前最大生产差距是什么？

production Provider wiring 未实现：compose 是 fake embedding + in-memory capacity/routing，production profile 会主动拒绝启动。其次是 V2-G3 灾备完全缺失，以及本轮未在可用 Docker daemon 上重跑全套真实依赖门禁。

### Q34：DR 应该怎么做？

当前只可讲下一步设计，不能说已实现。需要定义跨 MySQL、Redis、Qdrant、Neo4j 的一致 backup set，生成 manifest/checksum，脱敏验证，按 canonical-first 顺序 restore，再做 projection/runtime reconciliation，最后自动测 RPO/RTO 并定期 drill。

### Q35：为什么运行时恢复不等于 DR？

运行时恢复处理 Worker 崩溃、pending message 或 PARTIAL projection；底层数据仍存在。DR 处理存储损坏、区域丢失或备份恢复，必须有独立 backup/restore 和演练证据。

### Q36：如果项目继续演进，你会先做什么？

先完成生产 Provider boundary 和 clean CI/Docker acceptance，再做 V2-G3。不会先加更多 Agent，因为当前主要风险不是功能数量，而是生产依赖、灾备和同批次验证证据。

## 7. 项目问题与解决过程

### 7.1 外部 API timeout

问题：天气/道路服务可能慢或失败。根因是外部依赖不可控。解决：显式 async timeout、circuit breaker、静态 fallback 与规范化错误。结果：依赖失败不阻塞完整链路且不泄漏凭证。

### 7.2 Worker crash 与 pending

问题：处理中崩溃可能留下未完成任务。解决：取消不 ACK，pending 超时后 XAUTOCLAIM，读取 checkpoint N+1 恢复。历史结果：message loss 0，recovery 最大 4.824 秒。

### 7.3 Optimistic lock 冲突

问题：两个写者可能覆盖 dispatch/runtime/memory。解决：SQLAlchemy `version_id_col`、expected version 与明确 409/冲突状态。历史 dispatch 20/20 冲突被拦截，silent overwrite 0。

### 7.4 Shared Memory 半写

问题：MySQL 成功而 Qdrant/Neo4j 部分失败。解决：投影 stage、canonical finalization、PARTIAL 状态、durable attempt 与 reconciler。历史 projection leak 为 0。

### 7.5 Runtime Override 竞态

问题：人工改状态与 Worker 进入下游节点同时发生。解决：稳定边界、per-thread lock、MySQL CAS、child checkpoint promotion。历史 boundary race 50 轮违规 0。

### 7.6 Frontend data truth

问题：mock fallback 会掩盖 API 故障。解决：API mode 禁止回退，统一 truth states。结果：空数据、未暴露、无权限与不可用不再混为一谈。

### 7.7 Security ON 性能

问题：JWT、RBAC、限流与审计增加请求成本。解决：缓存 JWKS、Redis token bucket、稳定 security metrics。历史 50 users 下 QPS 278.998、P95 270 ms、unexpected error 0。

### 7.8 Observability overhead 与 SLO

问题：大量指标可能增加延迟与 cardinality。解决：稳定 label、recording rules、独立 Prometheus/Grafana。最新 raw evidence API P95 66.022 ms，但 graph workflow P95 167.311 ms 暴露了真实优化点。

### 7.9 Windows 测试临时目录权限

问题：两个历史 temp 目录 ACL 拒绝访问，导致扫描告警。当前处理是不做破坏性删除，记录限制并使用可访问 basetemp 完成测试。该问题仍是环境清洁债务。

### 7.10 本地 `.env` 配置漂移

问题：真实被忽略 `.env` 中 dev JWT secret 不满足 32 字符，默认 pytest 收集失败。通过进程级 `AUTHENTICATION_PROVIDER=disabled` 证明代码测试 833 pass，但默认门禁仍不健康。最终报告保留这个差距，没有修改用户 secret 配置。

## 8. 简历内容

### 项目名称

CountyFlow AI｜县域物流异常识别与智能调度系统

### 一句话描述

构建基于 FastAPI、Redis Streams、LangGraph 与多存储记忆的异步智能调度系统，支持崩溃恢复、运行时人工覆盖、跨存储一致性、安全审计和角色化运营前端。

### 技术栈

Python 3.12、FastAPI、LangGraph、SQLAlchemy、Alembic、MySQL、Redis Streams、Qdrant、Neo4j、Prometheus、Grafana、React 19、TypeScript、Vite、Vitest、Playwright、Docker Compose。

### 简历 Bullet

- 设计 8-Agent LangGraph 异步调度链路，将 API 与执行解耦，通过 Redis Streams consumer group、双 Worker、XAUTOCLAIM、DLQ 和 MySQL idempotency ledger 实现 effectively-once 业务效果；历史可靠性验收 message loss 与 duplicate dispatch 均为 0。
- 建立 MySQL Runtime Registry + Redis LangGraph Checkpointer 双层 Runtime Thread，在节点边界以 checkpoint ancestry、state version 和 CAS 推进，实现 Worker 崩溃后的 N+1 恢复；5 次历史恢复最大 4.824 秒。
- 实现 Runtime State Override，在 `environment → capacity` 稳定边界通过 Redis lock、MySQL CAS、`aupdate_state` 和 checkpoint promotion 安全完成车辆 `NORMAL → BROKEN`；历史 20 轮并发与 50 轮边界竞态违规 0。
- 构建 Qdrant Vector Memory、Neo4j Graph Memory 与 MySQL Shared Memory Control Plane，支持 CREATE/MERGE/REPLACE/CONFLICT、projection staging/finalization、PARTIAL reconciliation；历史并发 lost update 0、projection leak 0。
- 实现六角色 RBAC、JWT/OIDC/JWKS boundary、Redis 限流、durable security audit、敏感数据脱敏与 45 秒 single-use WebSocket ticket；Security ON 历史压测 50 users、P95 270 ms、unexpected error 0。
- 建立 46 个 metric family、9 条 recording rule、18 条 alert rule 与白色角色化 React App Shell；本轮验证后端 833 tests passed、前端 228 tests passed，lint/build 通过。

## 9. 诚实复盘

这个项目的优势是状态一致性、恢复协议和证据意识，而不是“用了很多技术名词”。真正值得讲的是：为什么 Redis 不是真相、为什么 checkpoint 需要 registry、为什么人工覆盖必须生成 child checkpoint、为什么投影不能先对读取侧可见、为什么 ACK 必须晚于 durable terminal。

同样要主动讲边界：当前 compose 是 docker-dev；LLM 没有接入当前图；真实 Capacity/Route provider 未实现；V2-G3 灾备不存在；本轮 Docker/E2E/性能未重跑；默认 pytest 受本地 `.env` 漂移影响。能准确说清这些限制，比笼统声称“生产级 COMPLETE”更能体现工程判断。
