# Task 7 实施报告：事件流与调度结果 API

## 基线与范围

- 固定 BASE：`b57aa6ce4dec656efc5f35a67fdf9bfdff33469c`
- 开始实施与报告编写时 HEAD：`b57aa6ce4dec656efc5f35a67fdf9bfdff33469c`
- 开始前工作树：干净。
- 本次只实现 Task 7 的图事件、结果响应模型、证据映射与必要的历史路网快照持久化扩展；未进入 Task 8 前端功能实现。

## TDD 红灯证据

先写行为测试，再运行失败，再做最小实现：

1. 事件与结果 API 红灯：
   - 命令：`python -m pytest backend/tests/api/test_task_events.py backend/tests/api/test_dispatch_tasks.py backend/tests/api/test_dispatch_api_e2e.py -q --basetemp .pytest-tmp-task7-red`
   - 结果：`3 failed, 37 passed`
   - 失败分别证明：容量事件缺少 `selected_vehicle_id`；主管结果缺少 `vehicle_allocation`；普通员工隐藏结果缺少新的 nullable 证据块。
2. 历史证据持久化红灯：
   - 命令：`python -m pytest backend/tests/unit/test_dispatch_service.py -q --basetemp .pytest-tmp-task7-persistence-red`
   - 结果：`2 failed, 12 passed`
   - 失败分别证明：调度节点没有传递 `road_network_nodes`；车辆证据没有持久化 `pickup_route`。
3. 首次真实沙盘 E2E 揭示严格模型验证失败：Task 5 的路由状态边缺少 `road_level`、`congestion_factor`、`weight_limit_tons`、`version`。修复位置在路由状态的来源投影，不放宽严格响应模型。

## 实现结果

### 实时图事件

- 容量事件在旧字段不变的基础上增加候选车辆、选中车辆与司机、是否换车、接驳路线和评分公式。
- 路由事件增加原路线、推荐路线、候选路线、阻塞边、距离/ETA 增量、访问节点数、DIJKSTRA 算法版本、路网版本以及完整节点/边。
- 调度事件增加原车辆、目标车辆和目标司机。
- 递归 JSON 安全转换覆盖 `Decimal`、枚举、日期时间、映射和序列；所有 Decimal 使用定点字符串，避免科学计数法及编码失败。
- 旧客户端依赖的事件名和旧字段保留；现有 WebSocket 行为与查询兼容测试通过。

### 严格响应模型与结果映射

- 新增显式、`extra=forbid`、严格 Pydantic 模型：`VehicleCandidateResponse`、`VehicleAllocationResponse`、`RoadNodeResponse`、`RoadEdgeResponse`、`PathResponse`、`RouteCandidateResponse`、`RoutePlanResponse`。
- `TaskResultResponse` 新增 nullable 的 `vehicle_allocation` 和 `route_plan`，OpenAPI 对上述组件及引用已有测试。
- 结果服务在同一个数据库 session 内加载 Dispatch 与 DispatchEvidence；只接受“恰好两条且类型集合恰为 `FLEET_ALLOCATION`、`ROUTE_CALCULATION`”的证据。
- 所有响应由显式白名单字段映射并再次经过严格模型验证；异常、重复、类型错误或结构错误的证据稳定归一化为两个 `null`，不回传未知字段、授权头或内部数据。
- Dispatch 行是原/目标车辆与目标司机的事实来源；证据列提供算法与路网版本；没有把任意 JSON 直接透传。

### 权限

- `route_visible` 同时控制旧的 `target_route_id`、`reason` 以及新的 `vehicle_allocation`、`route_plan`。
- 普通员工在方案未发布且不满足原可见性条件时，看不到车辆与路线详情；主管保持原权限可见。
- 已加入主管可见、员工不可见、畸形证据不可见、重复证据不可见测试。

## 完整历史路网快照来源

Task 6 原有 `ROUTE_CALCULATION.relevant_edges` 是紧凑审计摘要，不足以重建完整地图。Task 7 在受控白名单内扩展同一条路由计算证据：

`RoutingService` 生成版本化节点/边状态 → 调度 graph state → dispatch agent → `DispatchService` 白名单压缩 → `ROUTE_CALCULATION.payload.network_nodes/network_edges` → Result API 严格模型。

- 每次规划把当时使用的完整 18 节点、26 边和 `road_network_version` 与调度一并落库。
- `relevant_edges` 继续保留，兼容 Task 6 紧凑审计语义。
- 结果 API 和终态实时事件都读取同一次规划 state/持久证据语义；结果 API 绝不查询当前可变路网来冒充历史快照。
- 持久化仅允许地图与规划字段，不保存秘密、授权头或 provider 内部对象。

## 实际沙盘 E2E

- 车辆故障：实际扫描 `12` 辆车（包括原故障车辆作为不可用候选），选中 `V005` / `D003`，阻塞/相关边含 `E20`；候选数量由 `VEHICLES` 固定数据推导，未在响应逻辑中硬编码。
- 道路阻塞：`distance_delta_km=3.20`、`eta_delta_minutes=4`、阻塞边 `E04`；推荐边为 `E01,E06,E07,E08,E09`，确认绕开 `E04`。
- 两个场景的结果均含 `18` 个历史节点、`26` 条历史边，数量由沙盘 `ROAD_NODES/ROAD_EDGES` 推导。

## 验证记录

- 新增事件测试：`5 passed`。
- 新增三条事件/结果主测试首次绿灯：`3 passed`。
- DispatchService 单元测试：`14 passed`。
- 畸形/重复证据安全测试：通过。
- 四个 API/WebSocket 文件：`50 passed, 301 warnings in 57.08s`。
- Task 5/6 相关回归：`99 passed, 2 skipped in 29.99s`；两个跳过均为 opt-in MySQL 测试。
- 真实双场景沙盘 API → Redis stream → Worker → graph → SQLAlchemy 持久化 E2E：`1 passed`。
- `ruff check backend`：`All checks passed!`
- 完整 backend：`971 passed, 12 skipped, 810 warnings in 279.65s`。
- frontend lint：exit 0，`0 errors, 2 warnings`（既有 Fast Refresh 警告）。
- frontend Vitest：`52 passed` 文件、`242 passed` 测试。
- frontend build：成功，Vite 转换 `1917` 模块。
- `git diff --check`：exit 0；仅 Git 提示部分工作副本以后会由 LF 转 CRLF，无空白错误。
- 新增行敏感格式扫描：OpenAI 样式密钥、AWS 访问密钥、私钥头、URL 内嵌凭据、JWT 均为 `0` 命中。

## 偏差与环境说明

- Task 7 brief 示例提到 11 个候选，但当前固定沙盘实际定义并扫描 12 辆车辆，且原故障车辆作为有排除原因的候选具有解释价值；测试按 `VEHICLES` 的实际数据推导为 12，没有为匹配示例而硬编码或删候选。
- 为满足“完整历史路网而非当前路网”的要求，变更范围受控扩展到 Task 5 路由状态字段，以及 Task 6 的 agent/证据白名单链；没有改动权限基础规则或前端 Task 8。
- `COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV` 与 `SECURITY_DATABASE_URL` 均未设置，因此未声称运行真实 MySQL 集成；完整测试中的相关 MySQL/真实 Redis 测试按既有 opt-in 条件跳过。SQLite 真实仓储/Worker/graph 沙盘链已覆盖本任务行为。

## Critical 审查修复：事件发布边界

- 修复基线：`ae22794ad3d374960583460aa304e1e52a60c60e`，开始时工作树干净。
- RED：真实 HTTP ticket + WebSocket broker 的员工历史回放与实时推送测试为 `2 failed`；分别暴露 13 个路线敏感键和 7 个车辆/司机/接驳敏感键。
- 根因：一次性 ticket 未携带 `dispatch:review` 能力，且 WebSocket 历史与实时两个分支均直接执行 `event.to_dict()`。
- 修复：新增单一 `TaskEventVisibilityProjector` 服务端边界；snapshot、历史 replay、实时 live 都经同一 `project()` 发送。未发布非审核人员保留事件 envelope、`progress`、节点状态等非敏感数据，明确移除车辆、司机、接驳、路线、阻塞边、差值、算法/路网版本和路网节点/边键。
- 发布状态：每一条含敏感键的实时事件都打开一个有界 session 查询当前 `DispatchPublication`，不缓存建连时状态；同一员工连接中发布后的下一条事件立即可见。SQLAlchemy 查询失败时关闭式脱敏，不回显内部异常。
- 权限：ticket 只增加服务端生成并严格解析的 `can_review` 布尔值；主管/具 `dispatch:review` 权限者继续看到未发布详情，员工只有发布后可见，与 Result API `route_visible` 语义一致。
- GREEN：两条 Critical 测试 `2 passed`；WebSocket/ticket/Result 定向权限集 `28 passed`；四个 API/WebSocket 文件加 ticket 安全集 `68 passed`；跨实例 Redis broker 回归 `4 passed`；`ruff check backend` 通过。
- 本批按审查要求只修 Critical；两个 Important（事件递归白名单、持久证据身份/完整结构校验）留待后续批次，本批未运行完整 backend 全量测试。
