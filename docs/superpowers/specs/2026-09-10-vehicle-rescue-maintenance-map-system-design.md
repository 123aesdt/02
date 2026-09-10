# CountyFlow 车辆救援、维修复岗与双模式地图系统设计

**日期：** 2026-09-10

**状态：** 设计章节已确认，待书面规格复核

**视觉基准：** `docs/assets/ui-concepts/2026-09-10-repair-map-command-center-v8.png`

**关系：** 本规格扩展 `2026-09-02-fleet-rerouting-demo-design.md`。发生冲突时，以本规格关于车辆故障、救援、维修、自动复岗、地图和路线拓扑的定义为准。

## 1. 目标

CountyFlow 必须在员工上报车辆故障后形成可恢复、可解释、可审计的完整业务闭环，而不是只把车辆标记为不可用或停在故障点：

1. 原车安全停驶并停止承担当前配送。
2. 系统选择合格替代车辆和司机，计算到故障点的接驳路线。
3. 替代车完成货物接驳并沿订单剩余路线继续配送。
4. 系统分配救援车辆，将故障车沿路网送往维修站。
5. 系统创建维修工单、预留工位并按时间推进诊断、维修和安检。
6. 维修完成且安检通过后，车辆自动恢复为 `AVAILABLE` 并重新进入候选池。
7. 地图持续展示原车、替代车、救援车、维修站、路线与进度，所有业务覆盖层来自后端真实契约。

演示模式将两小时业务维修时间压缩为约一分钟，但保留真实业务时间字段。生产模式按真实时间运行。

## 2. 非目标

- 不实现跨县域大规模 VRP、多订单拆单或真实自动驾驶控制。
- 不把车辆维修结果交给 LLM 决定。
- 不让前端倒计时成为业务事实来源。
- 不要求答辩环境必须连接高德地图或互联网。
- 不将 Redis 作为车辆、救援、维修或调度的长期事实来源。
- 不改变 API 提交任务后通过 Redis Streams、Worker 和 LangGraph 异步执行的生产路径。

## 3. 总体架构

```text
员工上报故障
  → FastAPI 校验、持久化异常并 XADD 调度任务
  → Worker / LangGraph 识别故障与风险等级
  → FleetAllocationService 选择替代车辆和司机
  → RoutingService 计算接驳、继续配送、救援和拖返路线
  → IncidentResponseService 原子写入车辆状态、替代调度、救援任务、维修工单和 Outbox
  → Redis 任务事件 / WebSocket / REST 快照更新前端
  → MaintenanceProgressor 扫描 MySQL 到期工单并推进维修状态
  → 安检通过后 VehicleService 恢复车辆 AVAILABLE
```

MySQL 是订单、车辆、司机、调度、救援、维修、安检和审计的事实来源。Redis Streams 负责命令分发和实时事件。LangGraph 负责识别与决策，不在图内等待数小时。独立维修执行器根据数据库时间恢复和推进工作。

Agent 只能调用窄应用接口，不得直接导入 Redis、SQLAlchemy、Qdrant、Neo4j、高德 SDK 或其他厂商 SDK。

## 4. 应用接口与模块边界

### 4.1 车队与接驳

- `FleetProvider`：读取车辆、司机、资格、载重和位置快照。
- `FleetAllocationService.allocate_replacement(...)`：执行硬约束过滤、确定性评分和替代资源选择。
- `CargoTransferService.complete_transfer(...)`：以幂等方式记录接驳，更新订单当前车辆和司机。
- `VehicleService.transition(...)`：校验车辆状态转换并写入状态历史。

替代车辆必须满足车辆状态、司机状态、驾照、货物能力、剩余载重、道路限重和预计到达时间。候选评分与排除原因写入 `dispatch_evidence`。

### 4.2 路网与地图

- `RoadNetworkProvider`：返回指定版本的节点、道路边、站点与路况。
- `PathFinder`：在路网快照上计算路径，不依赖基础设施实现。
- `RoutingService`：生成替代车接驳、接管后配送、救援去程和拖返路线。
- `MapSnapshotQueryService`：组合路网、实体位置、路线进度和事件版本，输出统一地图快照。

业务路线必须由道路边 ID 序列组成。前端只能绘制后端返回的边序列，不能用起终点自由连线。为了区分同一道路上的重叠业务路线，前端可做不超过 6 像素的平行视觉偏移，但证据面板仍显示同一条真实道路边。

### 4.3 救援与维修

- `RescueOrchestrationService.create_mission(...)`：选择救援资源并创建唯一救援任务。
- `RescueProgressor.advance_due_missions(...)`：根据路线和时间推进救援车位置与任务状态。
- `MaintenanceOrchestrationService.schedule(...)`：创建维修工单并预留工位。
- `MaintenanceProgressor.advance_due_work(...)`：推进诊断、维修、安检和复岗。
- `SafetyInspectionService.evaluate(...)`：按风险规则决定自动安检或要求人工确认。

所有进度器使用可注入 `Clock`。生产时钟返回真实 UTC 时间；演示时钟使用 `demo_time_scale=120` 将演示经过时间映射到业务时间。

### 4.4 事件发布

领域状态和 Outbox 在同一 MySQL 事务写入。独立发布器将 Outbox 事件发送到 Redis；发布失败不会撤销已持久化状态，未发送事件会继续重试。

## 5. 状态机

### 5.1 车辆

```text
IN_TRANSIT
  → BROKEN
  → WAITING_RESCUE
  → IN_RESCUE
  → MAINTENANCE
  → QA_PENDING
  → AVAILABLE
```

安检失败进入 `OUT_OF_SERVICE`。`OUT_OF_SERVICE` 只能由具有维修或主管权限的人员重新开放，不允许计时器直接恢复。

### 5.2 救援任务

```text
CREATED → DISPATCHED → ARRIVED → LOADED → DELIVERED
```

可终止状态为 `DELIVERED`、`FAILED` 和 `CANCELLED`。失败记录规范化原因、尝试次数和最后位置；达到上限后进入人工处理队列。

### 5.3 维修工单

```text
SCHEDULED → WAITING_BAY → DIAGNOSING → REPAIRING → QA_PENDING → COMPLETED
```

可终止异常状态为 `FAILED` 和 `CANCELLED`。一般机械故障允许演示环境自动安检；制动、转向、事故、人员伤害和严重冷链故障必须由维修人员或主管确认。

## 6. 持久化模型

### 6.1 `fleet_vehicles`

保存 `vehicle_id`、车牌、类型、载重能力、货物能力、总重、状态、当前节点、当前位置进度、司机、当前任务和 `version`。`version` 使用 SQLAlchemy `version_id_col`。

### 6.2 `fleet_drivers`

保存 `driver_id`、姓名、驾照类型、值班状态、当前车辆、当前节点和 `version`。

### 6.3 `rescue_units`

保存救援车辆能力、状态、当前位置、可拖车型和 `version`。

### 6.4 `rescue_missions`

保存唯一 `mission_no`、故障车辆、救援车辆、故障节点、维修站、去程边序列、返程边序列、状态、进度、预计到达时间、尝试次数、幂等键和 `version`。

### 6.5 `maintenance_bays`

保存维修站、工位编号、能力、状态、当前工单和 `version`。

### 6.6 `maintenance_orders`

保存唯一工单号、车辆、救援任务、维修站、工位、故障分类、诊断、风险等级、状态、业务开始/到期时间、演示开始/到期时间、进度、安检模式、幂等键和 `version`。

### 6.7 `vehicle_status_history`

保存车辆每次转换的旧状态、新状态、原因、来源类型、来源标识、发生时间和实体版本。

### 6.8 路网与证据

继续使用 `road_nodes`、`road_edges`、`logistics_stations` 和 `dispatch_evidence`。路线证据保存道路边序列、路网版本、算法版本、距离、耗时、风险和被排除候选。

### 6.9 `domain_outbox`

保存事件 ID、聚合类型、聚合 ID、事件类型、序列号、载荷、创建时间、发布时间和尝试次数。事件 ID 与聚合序列共同防止重复发布和乱序应用。

## 7. 自动执行与恢复

维修和救援进度不通过长时间 `sleep` 推进。执行器周期查询到期记录，并用 `SELECT ... FOR UPDATE SKIP LOCKED` 在双 Worker 下领取工作。每次领取只完成一个合法状态转换，提交后再处理下一阶段。

车辆位置由路径边序列、阶段开始时间和预计持续时间计算。后端保存当前边、边内进度和位置版本；前端可在两个后端快照之间进行视觉插值，但不得改变业务到达状态。

服务重启后，执行器根据 MySQL 中的 `due_at` 和当前状态继续推进。演示倍率只影响 `DemoClock`；业务开始时间、业务预计完成时间和审计时间始终保留。

## 8. 风险分级自治

- 一般机械故障：自动安全停驶、换车、派救援、建单、维修、安检和复岗。
- 严重冷链、制动、转向、事故或人员伤害：立即执行安全与救援动作，但复岗必须人工确认。
- 无替代车辆：货物保持安全状态，任务进入资源等待并持续重新匹配。
- 无救援资源：保留唯一救援任务，按退避策略重新分配，不重复建单。
- 无维修工位：进入 `WAITING_BAY`，地图展示等待位置和预计入场时间。
- 并发预占冲突：捕获 `StaleDataError`，转换为 409 或内部冲突事件，再重新选择候选资源。

## 9. 双模式地图

### 9.1 统一契约

`MapSnapshot` 包含路网版本、边界、节点、道路边、车辆、救援资源、维修站、异常点、路线边序列、路线进度、地图范围和事件序列。

### 9.2 离线模式

答辩与 Docker development 默认使用内置 N01–N18、E01–E26 路网。离线地图采用已确认的现代浅色矢量风格，展示道路等级、路盾、水系、区域、POI、地图控件和业务覆盖层。

### 9.3 高德模式

生产配置可启用高德适配器。高德只提供底图、地理编码或外部路径输入；最终业务路线和调度证据仍由 CountyFlow 领域服务归一化并持久化。浏览器和服务端凭据通过环境变量配置并限制允许域名，禁止硬编码或写入日志。

高德或道路服务使用显式异步超时和熔断器。失败后在一秒内返回内置路网的静态安全路线，并在界面显示“离线底图”，不能回退为前端假数据。

## 10. API 与实时事件

新增只读接口：

- `GET /api/v1/map/snapshot?task_id=...`
- `GET /api/v1/fleet/vehicles`
- `GET /api/v1/rescue-missions/{mission_no}`
- `GET /api/v1/maintenance-orders`
- `GET /api/v1/maintenance-orders/{order_no}`

新增受权限保护的命令接口：

- `POST /api/v1/maintenance-orders/{order_no}/inspection-decisions`
- `POST /api/v1/rescue-missions/{mission_no}/retry`

实时事件至少包括：

- `VEHICLE_BREAKDOWN_CONFIRMED`
- `REPLACEMENT_ASSIGNED`
- `CARGO_TRANSFER_COMPLETED`
- `RESCUE_DISPATCHED`
- `RESCUE_PROGRESS_UPDATED`
- `RESCUE_ARRIVED`
- `TOW_STARTED`
- `VEHICLE_DELIVERED_TO_MAINTENANCE`
- `MAINTENANCE_STARTED`
- `MAINTENANCE_PROGRESS_UPDATED`
- `SAFETY_INSPECTION_REQUIRED`
- `MAINTENANCE_COMPLETED`
- `VEHICLE_RETURNED_TO_SERVICE`
- `MAP_SNAPSHOT_UPDATED`

事件包含稳定事件 ID、任务 ID、实体 ID、实体版本、序列号、发生时间和脱敏数据。WebSocket 断线后，前端使用 REST 快照和最后序列号恢复。

## 11. 前端产品面

- **运行态势：** 使用视觉基准中的地图与处置编排双栏，支持车辆选择、路线图层、全县视野、自动跟随和事件回放。
- **异常处置：** 展示员工上报、风险等级、候选资源、AI 解释和完整状态时间轴。
- **车辆与维修：** 展示车队状态、维修工位、工单、倒计时、安检、复岗历史和资源等待。
- **调度详情：** 展示原车、替代车、接驳记录、道路边证据、Agent 事件和审计结果。
- **员工任务：** 明确显示替代车辆、最新路线、救援状态和货物是否已接管。

桌面保持地图与处置面板双栏；窄窗口使用紧凑顶栏、地图、双列处置阶段和提前显示的维修摘要。交互控件支持键盘操作、可见焦点和 `prefers-reduced-motion`。

## 12. 错误处理

- Provider 错误统一转换为不含授权头、Key 或内部连接信息的领域错误。
- 地图不可用不影响已持久化的调度、救援和维修推进。
- Outbox 发布失败持续重试；重复事件由事件 ID 与序列号去重。
- 无法定位道路时不猜测节点，进入人工复核。
- 安检超时保持 `QA_PENDING`，绝不自动放行高风险车辆。
- 维修失败保留车辆 `OUT_OF_SERVICE`，并产生主管可见告警。

## 13. 测试策略

Phase 1 及之后严格执行 TDD：先写行为级失败测试并运行，再实现最小真实行为，最后运行回归。

- 单元测试：状态转换、演示时钟、维修进度、风险规则、候选评分、Dijkstra、路线边吸附和重叠路线表现契约。
- API 测试：上报、地图快照、车队/救援/维修读取、人工安检、幂等、409 和权限。
- Worker 测试：到期推进、双 Worker 领取、重启恢复、重复消息、退避和 Outbox 重发。
- Docker 集成测试：真实 MySQL、Redis 和双 Worker 下验证不重复派车、不重复建单、不重复复岗。
- 前端测试：地图适配器、图层筛选、倒计时、WebSocket 补偿、角色权限、响应式与无障碍。
- 浏览器 E2E：从员工上报到替代配送、救援拖返、维修、安检和自动复岗的完整链路。

## 14. 验收标准

1. 员工提交故障后，API 返回任务 ID，异步 Graph 启动且请求线程不执行完整 Graph。
2. 系统在演示场景三秒内产生替代车辆、救援任务、维修工单和可解释路线证据。
3. 原订单由替代车辆继续执行，故障车不再停留在异常点。
4. 地图路线全部引用路网边；不允许起终点自由直连。
5. 两小时演示维修约一分钟完成，刷新或重启后进度不重置。
6. 一般故障安检通过后车辆自动恢复 `AVAILABLE`；高风险故障等待人工确认。
7. 重复消息和双 Worker 并发不会产生重复调度、救援、工单或复岗记录。
8. 高德不可用时一秒内显示离线地图并继续业务处理。
9. 1440×900 无裁切；686 像素宽无横向溢出，核心维修摘要在前两屏内可见。
10. `ruff check backend`、`pytest`、前端 lint/test/build、目标 Docker 集成测试和 `git -c safe.directory=<workspace> diff --check` 全部通过后才能声明完成。

## 15. 展示脚本

完整演示控制在约 90 秒：员工上报故障；系统完成风险识别、换车和救援编排；地图显示替代接驳、接管配送、救援去程和拖返；替代车继续订单；故障车进入维修站；维修倒计时推进；安检通过；车辆恢复 `AVAILABLE` 并重新出现在候选车队中。
