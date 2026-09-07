# Task 6 实施报告：调度持久化、并发预占、审计与发布

## 基线与范围

- 固定 BASE：`c28040d5cfa2b076ccb25c5a9d4f5f3149ce1dc6`
- 报告编写时 HEAD（提交前）：`c28040d5cfa2b076ccb25c5a9d4f5f3149ce1dc6`
- 开始前检查：HEAD 等于 BASE，工作树干净。
- 实施范围：仅 Task 6；未进入 Task 7。

## TDD 红灯证据

1. 持久化与并发首轮：`6 passed, 4 failed`。失败核心为 `DispatchService.execute()` 尚不接受 `original_vehicle_id` 等新参数，证明新事务行为尚未实现。修正测试资源释放后再次运行，得到无数据库锁噪声的同一接口红灯。
2. 审计、Agent 与发布首轮：`7 failed`。失败分别证明车辆冲突未转人工复核、四项新增审计检查不存在/无效、紧凑候选与路径证据未保存、换车发布指令缺少确定性字段。
3. 运力证据投影：离线图测试以 `KeyError: cargo_capability` 失败，证明真实图链路未把冷链能力送达审计。
4. 候选顺序：测试输入以 V-006 为首选、V-005 分数更高；旧实现错误选择 V-005，证明服务擅自重排上游候选。修复后严格保留输入顺序。
5. 完整后端首轮：`940 passed, 10 skipped, 1 failed in 255.34s`。唯一失败为窄测试替身仅接受位置参数，而 Dispatch Agent 改为关键字调用。根因复现后恢复位置参数调用，同时仍传递五个新增参数。
6. 新增车辆预占冲突审计边界：实现前实际返回 `APPROVED`，单测为 `1 failed`；将 `VEHICLE_RESERVATION_CONFLICT` 纳入人工复核集合后，审计集 `15 passed`。

## 实现结果

### 原子持久化与乐观锁

- `DispatchService.execute` 接收原车、已排序候选、接驳节点、车队证据和路线证据。
- 每次候选尝试在独立 Session/单事务内完成：读取任务与幂等结果、检查目标车辆 `AVAILABLE`、更新为 `RESERVED`、写入 Dispatch、写入恰好两条 DispatchEvidence、提交终态。
- 使用现有 ORM `version_id_col`；捕获 SQLAlchemy `StaleDataError` 并转为候选预占冲突。没有使用客户端版本值的 Python 比较模拟乐观锁。
- 仅尝试上游排序中前两个合格候选：首选冲突后只尝试下一候选一次；没有下一候选时抛出 `VEHICLE_RESERVATION_CONFLICT`，Agent 转入人工复核。
- 最终 Dispatch 的司机来自实际预占成功候选，不沿用原司机。
- `task_id` 幂等重放返回已持久化 Dispatch；不再预占车辆，也不追加证据。
- 金额/距离/运力数据继续使用 `Decimal` 或无损字符串化，不引入浮点精度损失。

### 真实并发覆盖

- SQLite 默认测试使用两个真实 SQLAlchemy Session、两个线程和 `Barrier`；通过 Session 加载事件确保竞争双方读取同一车辆版本，然后真实提交触发一方 `StaleDataError`。
- 两候选场景验证两个任务分别获得 V-005/V-006，且每个 Dispatch 恰好两条证据。
- 单候选场景验证一个成功、另一个得到 `VEHICLE_RESERVATION_CONFLICT`。
- 另保留 opt-in MySQL 同行为测试；本机未设置 `COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV`，因此如实跳过，未声称运行 MySQL。

### 审计与发布

- 审计新增 `vehicle_assignment`、`capacity_constraint`、`route_connectivity`、`blocked_edge_exclusion`。
- 故障换车校验原车与目标车不同、目标与实际 Dispatch/选中候选一致、候选合格、剩余载重足够、冷链货物具备冷链能力。
- 堵塞路线校验节点/边逐段连通并排除所有阻断边，支持双向道路反向通行。
- 审计只持久化候选的车辆 ID、分数、合格状态、排除原因，以及路径节点/边 ID 和阻断边 ID；未保存授权头或原始供应商载荷。
- 换车发布指令确定性包含目标车牌、司机姓名与编号、接驳节点、目标路线；保持 action-only 和既有权限检查。

## 必要支持改动与偏差

为让 Task 6 的冷链审计规则在真实 Task 4/5 图链路中可用，窄范围补充了以下支持字段：

- Fleet 候选模型/服务增加 `cargo_capability`；
- Capacity Agent 将该字段投影到图状态；
- Graph state 增加 Task 6 所需的候选、路径、接驳及实际调度结果字段；
- 离线图测试补充冷链能力断言。

这些改动只传递 Task 6 审计所需证据，不新增 Task 7 功能。由于工作树的 Windows deny-read ACL，`apply_patch` 无法读取目标文件；按约束改用唯一匹配的完整函数/类块 PowerShell 写入，每次立即执行 `py_compile` 与 `git diff`。未使用含反引号换行的 Replace。

## 实际验证

- Task 6 持久化/并发中间绿灯：`10 passed in 6.83s`。
- 审计/Agent/发布相关绿灯：`20 passed in 9.92s`。
- 运力与离线图回归：`14 passed`。
- 候选顺序与并发：`12 passed, 1 skipped`。
- Task 1/4/5/6 相关回归：`123 passed, 3 skipped in 27.28s`。
- 最终 Task 6 聚焦：`32 passed, 1 skipped in 18.05s`；跳过项为未配置的 opt-in MySQL 测试。
- `\.venv\Scripts\python.exe -m ruff check backend`：`All checks passed!`
- 最终完整后端 pytest（会话 5465，真实 exit code 0）：`943 passed, 10 skipped, 768 warnings in 264.52s`。
- `git -c safe.directory=<workspace> diff --check`：exit code 0；仅输出 Git 的 LF/CRLF 工作树提示，无空白错误。
- 新增行敏感特征扫描：OpenAI 样式密钥 0、AWS 访问密钥 0、私钥头 0、URL 内嵌凭据 0、JWT 样式令牌 0；扫描不回显匹配内容。

## 已知问题与阻塞

- MySQL opt-in 并发测试未运行，因为本机未设置可用的 `COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV`。SQLite 双 Session/Barrier 并发测试已实际运行并验证 `StaleDataError` 路径。
- 完整测试的 768 条警告为 FastAPI 生命周期弃用、Starlette/httpx 兼容及 Qdrant 版本探测等既有警告；没有测试失败。
- 无实现阻塞。

## 独立审查 Important #1 修复批次

- 审查修复起点：`fa3d17037f287b33933b443f9e74cf9dd14f18ca`，起点工作树干净。
- 本批次只修复“同一 `task_id` 并发重放可产生重复 Dispatch”；未处理审查报告 Important #2–#5，按协调要求也未重复运行完整后端全量。
- 红灯：SQLite 两个真实 Session、Barrier、同 task 但分别选择 V-005/V-006，旧实现数据库实况为 `2 Dispatch / 4 Evidence / 2 RESERVED`；连同 ORM 唯一约束缺失和迁移文件缺失，共 `3 failed, 1 skipped`。
- 数据库约束：ORM 新增 `uq_dispatches_task_id`；新增 Alembic `20260907_14_dispatch_task_uniqueness.py`，接续 `20260902_13`，upgrade 创建唯一约束、downgrade 删除约束，不修改旧迁移。
- 竞争回读：服务仍先查询幂等结果；insert/flush/commit 的 `IntegrityError` 会先回滚原事务，再用全新 Session 按外部 task_id 查任务并回读赢家。仅确认同 task Dispatch 已存在时返回该结果；否则原样抛出 IntegrityError。
- 回滚结果：并发输家的车辆状态与 Dispatch/Evidence 写入均随原事务回滚；最终两个调用返回同一 Dispatch，数据库为 `1 Dispatch / 2 Evidence / 1 RESERVED`，另一候选车保持 `AVAILABLE`。
- 额外回归：人为制造非 task 唯一约束的 `dispatch_no` 冲突，验证服务不会将其误吞为幂等竞争。
- 首次绿灯：新增同 task 并发、ORM 约束、SQLite 迁移往返为 `3 passed, 1 skipped`。
- 最终相关回归：`24 passed, 4 skipped in 7.16s`，覆盖 Dispatch 单测、全部车辆并发测试和全部迁移测试；4 个跳过均为未配置的 opt-in MySQL 项。
- Alembic head：`20260907_14 (head)`。
- MySQL 状态：本机未设置 `COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV`，新增 MySQL 唯一约束往返与同 task 并发测试均如实跳过；未声称运行 MySQL。
- Important #1 批次 Ruff：`All checks passed!`。
- Important #1 暂存差异 `diff --check`：exit code 0；敏感特征扫描五类均为 0。

## 独立审查 Important #2–#5 修复批次

- 修复起点：`c47db72c0c2d4441bdc4bf7f9466a87ad0df8abb`，起点工作树干净；本批未进入 Task 7。
- TDD 红灯：车辆/司机独立事实、未声明阻塞边、真实反向边和生产候选投影首轮为 `8 failed in 3.68s`；持久证据重放单测首轮以缺失 `selected_candidate` 的 `KeyError` 失败。
- 车辆审计不再只信 `eligible`：同时校验预占前车辆为 `AVAILABLE`、司机为 `ON_DUTY`/`AVAILABLE`、排除原因为空、运力与货类匹配，并校验候选、图状态和持久 Dispatch 的车辆/司机 ID 三方一致。
- 路线审计同时校验声明阻断边和紧凑路网快照中的 `status`；推荐路径上任一边为 `BLOCKED` 均拒绝。RoutingService 真实投影补齐 `bidirectional`，真实 Dijkstra 反向路径可由 AuditService 审核通过。
- Task 4 生产候选链路从 `FleetVehicleSnapshot` 传递 `vehicle_status`、`driver_status`、精确字符串 `remaining_capacity_kg` 和评分分量；Decimal 边界未转为浮点。
- DispatchEvidence 的车队证据只对实际成功候选保存完整审计白名单，其他候选只保存 ID、score 和 reasons；路线证据仅保存原路线、推荐路线、接驳路径、阻断边及这些路径/阻断相关边。
- AuditRecord 保存重放所需的货物重量/类型、实际 Dispatch 原/目标车辆与司机、所选候选完整校验事实、路径 ID、阻断 ID 和相关边；未保存原始请求、授权字段或整张路网。
- 9 条审查探针绿灯：车辆/司机、阻断状态、真实反向边和生产投影 `8 passed in 3.35s`；持久证据重放及四类篡改拒绝 `1 passed in 2.06s`。
- 相关回归：项目 `.venv` 下 `119 passed, 4 skipped in 29.19s`，覆盖 Fleet、RoadNetwork、Capacity、Routing、离线图、真实 SQL 图、Dispatch、并发、Audit、Publication 和相关迁移；4 个跳过均为未配置的 opt-in MySQL。
- 格式化后关键回归：`50 passed in 14.87s`；完整 backend Ruff：`All checks passed!`。
- 系统 Python 曾在收集迁移测试时命中不完整同名 Alembic 包，报 `ModuleNotFoundError: alembic.migration`；改用项目 `.venv` 后相关迁移与回归通过，此项不是产品代码失败。
- Windows deny-read ACL 仍使 `apply_patch` 无法读取目标文件；按约束仅用完整函数/方法块 PowerShell 写入并立即 `py_compile`/diff，机械格式使用 Ruff。

- 提交前最终相关回归：`119 passed, 4 skipped in 29.69s`；未启动完整后端全量，按协调要求留待五项审查修复汇总后统一执行。
