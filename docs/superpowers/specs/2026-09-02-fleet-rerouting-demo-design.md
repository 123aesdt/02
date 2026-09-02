# CountyFlow 车辆重调度与离线路线重算设计

**日期：** 2026-09-02

**状态：** 已确认，待实施计划

**适用环境：** `local`、`test`、`docker-dev`

## 1. 目标

在现有异步链路“前端 → FastAPI → Redis Streams → Worker → LangGraph → MySQL/Qdrant/Neo4j → WebSocket/状态查询 → 前端”内补齐两个可验证的业务闭环：

1. 输入车辆故障后，系统查询完整虚拟车队，过滤不合格车辆，计算候选车辆得分，选择替代车辆和司机，计算接驳路径并持久化换车调度结果。
2. 输入道路堵塞后，系统更新虚拟路网边状态，使用本地 Dijkstra 算法重新计算路径，输出新旧路线的节点、道路、里程、时长、风险和选择依据。

所有演示业务数据均为“新平县数字沙盘”虚拟数据。系统不调用高德、百度或其他在线地图服务。展示结果必须来自后端算法、事件和 MySQL 持久化数据，前端不得自行构造决策结果。

## 2. 非目标

- 不接入真实地图、车联网、司机终端或企业调度平台。
- 不实现跨县域的大规模车辆路径问题（VRP）、多订单拆单优化或实时 GPS 轨迹。
- 不新增只用于展示的 Agent，不将规则计算交给 LLM。
- 不改变 Redis Streams 的任务提交、幂等、重试、`XAUTOCLAIM` 和终态持久化后 `XACK` 约束。

## 3. 方案选择

采用“增强现有 8 Agent + MySQL 虚拟沙盘 + 本地 Dijkstra”的方案：

- `capacity` Agent 扩展为车队运力评估与替代车辆选择，但仍通过窄接口调用应用服务。
- `routing` Agent 从虚拟路网计算接驳路径与配送路径，不再从固定候选路线列表直接挑选名称。
- `dispatch` Agent 原子持久化目标车辆、目标司机、目标路线和计算证据。
- `audit` Agent 校验车辆约束、路径连通性、阻塞边排除和持久化一致性。

不新增第 9 个 Agent，以保持现有 Agent 编排、监控指标、检查点和演示叙事稳定。

## 4. Agent 数据流

```text
异常输入
  → intake：结构化车辆故障或道路堵塞，定位故障节点或受影响道路边
  → entity_memory / graph_memory：提供历史处置证据，不直接决定车辆或路线
  → environment：生成虚拟天气和道路风险输入
  → capacity：评估原车辆；必要时扫描车队、过滤候选并选择替代车辆/司机
  → routing：移除阻塞边；计算接驳路径、最快/最短/最安全配送路径并选优
  → dispatch：原子预占车辆并写入调度与证据
  → audit：验证载重、冷链、司机、车辆状态、路径和阻塞边排除
  → WebSocket / result API：返回可解释证据
```

车辆故障但存在合格替代车辆时，`capacity_status` 为 `REASSIGNED`，任务继续进入路径规划。仅在没有合格车辆时返回 `UNAVAILABLE` 并进入人工复核。

## 5. 模块边界

### 5.1 车队调度

- `FleetProvider`：读取车辆、司机及位置快照；生产运行实现只访问 MySQL。
- `TravelTimeEstimator`：计算候选车辆到异常节点的距离与预计时间；车队服务不直接导入路网数据库实现。
- `FleetAllocationService`：执行硬约束过滤、评分和确定性选优。
- `capacity` Agent：把图状态转换为服务输入，再把服务结果写回图状态。

### 5.2 路网计算

- `RoadNetworkProvider`：按路网版本读取节点、道路边和站点映射；生产运行实现只访问 MySQL。
- `PathFinder`：纯算法接口，输入路网快照、起终点、车辆约束和目标函数，输出路径计算结果。
- `DijkstraPathFinder`：不依赖外部地图或网络请求的确定性实现。
- `RoutingService`：分别计算最快、最短、最安全路线，去重后按综合分选优。
- `routing` Agent：组合异常、车队选择、环境和记忆结果，生成路线证据。

### 5.3 持久化和发布

- `DispatchService`：在同一 MySQL 事务中预占车辆、写入调度和证据。
- `DispatchRepository`：继续使用 SQLAlchemy 乐观锁；车辆实体也使用 `version_id_col`。
- `DispatchPublicationService`：发布审核通过的目标车辆、司机、路线和行驶说明。

Agent 不得直接导入 SQLAlchemy、Redis、Qdrant、Neo4j 或厂商 SDK。

## 6. MySQL 数据模型

### 6.1 `logistics_stations`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `station_id` | varchar(64) | 唯一、非空 |
| `name` | varchar(128) | 非空 |
| `station_type` | varchar(32) | `HUB`、`TOWN`、`VILLAGE`、`COLD_CHAIN`、`MAINTENANCE` |
| `road_node_id` | varchar(64) | 非空，关联沙盘节点标识 |
| `handling_capacity_kg` | decimal(12,2) | 非空 |
| `status` | varchar(32) | `ACTIVE` 或 `CLOSED` |

### 6.2 `fleet_drivers`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `driver_id` | varchar(64) | 唯一、非空 |
| `name` | varchar(64) | 非空 |
| `license_class` | varchar(16) | 非空 |
| `status` | varchar(32) | `ON_DUTY`、`BUSY`、`OFF_DUTY`、`SUSPENDED` |
| `current_vehicle_id` | varchar(64) | 可空 |
| `current_node_id` | varchar(64) | 非空 |
| `version` | integer | SQLAlchemy `version_id_col` |

### 6.3 `fleet_vehicles`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `vehicle_id` | varchar(64) | 唯一、非空 |
| `plate_no` | varchar(32) | 唯一、非空 |
| `vehicle_type` | varchar(32) | `VAN`、`REFRIGERATED_VAN`、`LIGHT_TRUCK`、`ELECTRIC_VAN`、`TRICYCLE` |
| `max_load_kg` | decimal(10,2) | 非空 |
| `current_load_kg` | decimal(10,2) | 非空 |
| `cargo_capability` | varchar(32) | `GENERAL`、`COLD_CHAIN`、`FARM_SUPPLY` |
| `gross_weight_tons` | decimal(6,2) | 非空 |
| `status` | varchar(32) | `AVAILABLE`、`RESERVED`、`IN_TRANSIT`、`BROKEN`、`MAINTENANCE` |
| `current_node_id` | varchar(64) | 非空 |
| `assigned_driver_id` | varchar(64) | 可空 |
| `version` | integer | SQLAlchemy `version_id_col` |

剩余载重按 `max_load_kg - current_load_kg` 计算，不单独持久化。

### 6.4 `road_nodes`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `node_id` | varchar(64) | 唯一、非空 |
| `name` | varchar(128) | 非空 |
| `x_km` | decimal(8,2) | 虚拟平面横坐标 |
| `y_km` | decimal(8,2) | 虚拟平面纵坐标 |
| `node_type` | varchar(32) | `STATION`、`JUNCTION`、`BRIDGE`、`INCIDENT_POINT` |

### 6.5 `road_edges`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `edge_id` | varchar(64) | 唯一、非空 |
| `name` | varchar(128) | 非空 |
| `from_node_id` | varchar(64) | 非空 |
| `to_node_id` | varchar(64) | 非空 |
| `distance_km` | decimal(8,2) | 非空 |
| `base_minutes` | integer | 非空 |
| `road_level` | varchar(32) | `NATIONAL`、`COUNTY`、`TOWN`、`VILLAGE` |
| `risk_level` | varchar(16) | `LOW`、`MEDIUM`、`HIGH` |
| `status` | varchar(32) | `OPEN`、`CONGESTED`、`BLOCKED`、`RESTRICTED` |
| `congestion_factor` | decimal(5,2) | 默认 `1.00` |
| `weight_limit_tons` | decimal(6,2) | 非空 |
| `bidirectional` | boolean | 本设计种子数据均为 `true` |
| `version` | integer | 路况变更时递增 |

### 6.6 `dispatch_evidence`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | bigint | 主键 |
| `dispatch_id` | bigint | 外键，非空 |
| `evidence_type` | varchar(32) | `FLEET_ALLOCATION`、`ROUTE_CALCULATION` |
| `algorithm_version` | varchar(32) | `FLEET_SCORE_V1` 或 `DIJKSTRA_V1` |
| `payload_json` | json | 候选、分项评分、路径和比较值 |
| `road_network_version` | integer | 路线证据必填 |

`dispatches` 新增 `original_vehicle_id`、`target_vehicle_id`、`transfer_node_id`；继续使用已有 `original_driver_id`、`target_driver_id`、`original_route_id`、`target_route_id` 和 `version`。

`orders` 新增 `cargo_weight_kg`、`cargo_type`、`origin_station_id`、`destination_station_id`。

`anomalies` 新增 `incident_node_id`、`affected_edge_id`。自然语言无法唯一定位道路时不猜测，进入人工复核。

## 7. 完整虚拟种子数据

### 7.1 站点（8 个）

| ID | 名称 | 类型 | 节点 | 处理能力 kg | 状态 |
|---|---|---|---|---:|---|
| ST-001 | 新平县中心仓 | HUB | N01 | 20000 | ACTIVE |
| ST-002 | 城东配送站 | TOWN | N06 | 6000 | ACTIVE |
| ST-003 | 北岭村驿站 | VILLAGE | N11 | 1200 | ACTIVE |
| ST-004 | 河西乡服务站 | TOWN | N12 | 3500 | ACTIVE |
| ST-005 | 南山村服务点 | VILLAGE | N13 | 1000 | ACTIVE |
| ST-006 | 新平冷链中心 | COLD_CHAIN | N14 | 5000 | ACTIVE |
| ST-007 | 县域车辆维修站 | MAINTENANCE | N15 | 2500 | ACTIVE |
| ST-008 | 城东电商服务点 | TOWN | N17 | 2800 | ACTIVE |

### 7.2 路网节点（18 个）

| ID | 名称 | 坐标 km | 类型 |
|---|---|---|---|
| N01 | 新平县中心仓 | (0.00, 0.00) | STATION |
| N02 | 西环路口 | (2.00, 0.00) | JUNCTION |
| N03 | 新平路西口 | (2.00, 2.00) | JUNCTION |
| N04 | 新平路 K3.2 | (5.00, 2.00) | INCIDENT_POINT |
| N05 | 东河桥 | (8.00, 2.00) | BRIDGE |
| N06 | 城东配送站 | (10.00, 2.00) | STATION |
| N07 | 102 国道西口 | (2.00, -2.00) | JUNCTION |
| N08 | 102 国道中段 | (6.00, -2.00) | JUNCTION |
| N09 | 102 国道东口 | (9.00, -1.00) | JUNCTION |
| N10 | 308 县道口 | (0.00, 3.00) | JUNCTION |
| N11 | 北岭村驿站 | (4.00, 6.00) | STATION |
| N12 | 河西乡服务站 | (-3.00, 2.00) | STATION |
| N13 | 南山村服务点 | (7.00, -5.00) | STATION |
| N14 | 新平冷链中心 | (1.00, -1.00) | STATION |
| N15 | 县域车辆维修站 | (4.00, 1.00) | STATION |
| N16 | 河西农资路口 | (-1.00, 4.00) | JUNCTION |
| N17 | 城东电商服务点 | (11.00, 4.00) | STATION |
| N18 | 双河村路口 | (12.00, 0.00) | JUNCTION |

### 7.3 道路边（26 条，均双向）

种子初始化时所有边为 `OPEN`、拥堵倍率为 `1.00`。道路堵塞场景把 E04 改为 `BLOCKED`。

| ID | 名称 | 起点—终点 | km | 分钟 | 等级 | 风险 | 限重 t |
|---|---|---|---:|---:|---|---|---:|
| E01 | 中心仓连接线 | N01—N02 | 1.50 | 3 | COUNTY | LOW | 8.0 |
| E02 | 西环至新平路 | N02—N03 | 1.50 | 3 | COUNTY | LOW | 8.0 |
| E03 | 新平路西段 | N03—N04 | 2.00 | 4 | COUNTY | MEDIUM | 6.0 |
| E04 | 新平路东河桥段 | N04—N05 | 2.50 | 5 | COUNTY | HIGH | 6.0 |
| E05 | 东河桥连接线 | N05—N06 | 2.50 | 5 | TOWN | LOW | 5.0 |
| E06 | 102 国道引道 | N02—N07 | 2.00 | 4 | COUNTY | LOW | 10.0 |
| E07 | 102 国道西段 | N07—N08 | 4.00 | 7 | NATIONAL | LOW | 20.0 |
| E08 | 102 国道东段 | N08—N09 | 3.20 | 6 | NATIONAL | LOW | 20.0 |
| E09 | 国道至城东站 | N09—N06 | 2.50 | 4 | COUNTY | LOW | 8.0 |
| E10 | 中心仓至 308 线 | N01—N10 | 3.10 | 6 | COUNTY | MEDIUM | 8.0 |
| E11 | 308 县道北岭段 | N10—N11 | 5.50 | 11 | COUNTY | MEDIUM | 5.0 |
| E12 | 308 县道农资段 | N10—N16 | 2.00 | 4 | COUNTY | LOW | 7.0 |
| E13 | 河西农资支线 | N16—N12 | 4.00 | 8 | TOWN | LOW | 5.0 |
| E14 | 河西回仓线 | N12—N01 | 3.60 | 7 | TOWN | LOW | 5.0 |
| E15 | 102 国道南山支线 | N08—N13 | 4.50 | 9 | VILLAGE | MEDIUM | 3.5 |
| E16 | 南山东接线 | N13—N09 | 5.20 | 10 | VILLAGE | MEDIUM | 3.5 |
| E17 | 城东电商北线 | N06—N17 | 3.50 | 7 | TOWN | LOW | 5.0 |
| E18 | 电商双河线 | N17—N18 | 4.00 | 8 | VILLAGE | LOW | 3.5 |
| E19 | 双河城东线 | N18—N06 | 2.80 | 6 | VILLAGE | LOW | 3.5 |
| E20 | 维修站接驳线 | N15—N04 | 2.80 | 6 | TOWN | LOW | 5.0 |
| E21 | 维修站国道线 | N15—N08 | 3.00 | 6 | COUNTY | LOW | 8.0 |
| E22 | 冷链中心回仓线 | N14—N01 | 1.10 | 3 | TOWN | LOW | 5.0 |
| E23 | 冷链中心国道线 | N14—N07 | 2.50 | 5 | COUNTY | LOW | 8.0 |
| E24 | 北岭电商山路 | N11—N17 | 8.00 | 15 | VILLAGE | HIGH | 2.0 |
| E25 | 东河桥电商线 | N05—N17 | 3.10 | 6 | TOWN | LOW | 5.0 |
| E26 | 国道双河线 | N09—N18 | 3.30 | 6 | COUNTY | LOW | 8.0 |

### 7.4 司机（10 名）

| ID | 姓名 | 驾照 | 状态 | 当前车辆 | 节点 |
|---|---|---|---|---|---|
| D-001 | 李师傅 | C1 | BUSY | V-001 | N04 |
| D-002 | 张师傅 | C1 | ON_DUTY | V-002 | N01 |
| D-003 | 陈师傅 | C1 | ON_DUTY | V-005 | N15 |
| D-004 | 王师傅 | B2 | BUSY | V-004 | N06 |
| D-005 | 林师傅 | C1 | OFF_DUTY | V-006 | N14 |
| D-006 | 黄师傅 | C1 | ON_DUTY | V-007 | N12 |
| D-007 | 周师傅 | B2 | ON_DUTY | V-008 | N03 |
| D-008 | 徐师傅 | C1 | BUSY | V-009 | N11 |
| D-009 | 郭师傅 | B2 | ON_DUTY | V-010 | N01 |
| D-010 | 杨师傅 | C1 | ON_DUTY | V-012 | N06 |

### 7.5 车辆（12 辆）

| ID | 车牌 | 类型 | 最大/当前载重 kg | 总重 t | 能力 | 状态 | 节点 | 司机 |
|---|---|---|---:|---:|---|---|---|---|
| V-001 | 新物冷链-01 | REFRIGERATED_VAN | 1500/700 | 2.80 | COLD_CHAIN | IN_TRANSIT | N04 | D-001 |
| V-002 | 新物厢货-02 | VAN | 1200/200 | 2.20 | GENERAL | AVAILABLE | N01 | D-002 |
| V-003 | 新物厢货-03 | VAN | 1000/600 | 2.00 | GENERAL | AVAILABLE | N15 | — |
| V-004 | 新物轻卡-04 | LIGHT_TRUCK | 3000/1200 | 5.50 | FARM_SUPPLY | IN_TRANSIT | N06 | D-004 |
| V-005 | 新物冷链-05 | REFRIGERATED_VAN | 1000/100 | 2.40 | COLD_CHAIN | AVAILABLE | N15 | D-003 |
| V-006 | 新物电运-06 | ELECTRIC_VAN | 900/0 | 1.80 | GENERAL | MAINTENANCE | N14 | D-005 |
| V-007 | 新物乡配-07 | TRICYCLE | 300/50 | 0.80 | GENERAL | AVAILABLE | N12 | D-006 |
| V-008 | 新物轻卡-08 | LIGHT_TRUCK | 2000/700 | 4.50 | GENERAL | AVAILABLE | N03 | D-007 |
| V-009 | 新物冷链-09 | REFRIGERATED_VAN | 1600/500 | 3.00 | COLD_CHAIN | IN_TRANSIT | N11 | D-008 |
| V-010 | 新物农运-10 | LIGHT_TRUCK | 4000/1000 | 6.50 | FARM_SUPPLY | AVAILABLE | N01 | D-009 |
| V-011 | 新物冷链-11 | REFRIGERATED_VAN | 1800/1300 | 3.20 | COLD_CHAIN | AVAILABLE | N14 | — |
| V-012 | 新物电运-12 | ELECTRIC_VAN | 1000/300 | 2.00 | GENERAL | AVAILABLE | N06 | D-010 |

### 7.6 订单（12 张）

| 订单 | 货物 | kg | 起点→终点 | 车辆 | 状态 |
|---|---|---:|---|---|---|
| DEMO-ORDER-001 | COLD_CHAIN | 700 | ST-001→ST-002 | V-001 | IN_TRANSIT |
| DEMO-ORDER-002 | FARM_SUPPLY | 1200 | ST-001→ST-003 | V-010 | PENDING |
| DEMO-ORDER-003 | COLD_CHAIN | 500 | ST-003→ST-001 | V-009 | IN_TRANSIT |
| DEMO-ORDER-004 | GENERAL | 300 | ST-001→ST-008 | V-012 | PENDING |
| DEMO-ORDER-005 | GENERAL | 850 | ST-001→ST-002 | V-008 | IN_TRANSIT |
| DEMO-ORDER-006 | COLD_CHAIN | 450 | ST-006→ST-003 | V-011 | PENDING |
| DEMO-ORDER-007 | FARM_SUPPLY | 1600 | ST-004→ST-001 | V-010 | PENDING |
| DEMO-ORDER-008 | GENERAL | 260 | ST-008→ST-005 | V-012 | PENDING |
| DEMO-ORDER-009 | GENERAL | 900 | ST-001→ST-007 | V-004 | IN_TRANSIT |
| DEMO-ORDER-010 | COLD_CHAIN | 600 | ST-003→ST-002 | V-009 | PENDING |
| DEMO-ORDER-011 | GENERAL | 400 | ST-001→ST-004 | V-002 | PENDING |
| DEMO-ORDER-012 | COLD_CHAIN | 300 | ST-006→ST-002 | V-005 | PENDING |

订单 001 用于车辆故障演示，订单 005 用于道路堵塞演示。

## 8. 异常场景

### 8.1 车辆故障

输入：`新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。`

结构化结果：

```json
{
  "anomaly_type": "VEHICLE_BREAKDOWN",
  "issue_subtype": "ENGINE",
  "vehicle_id": "V-001",
  "vehicle_status": "BROKEN",
  "incident_node_id": "N04",
  "order_id": "DEMO-ORDER-001"
}
```

V-005 是唯一满足冷链、载重、车辆状态、司机状态和路径可达性全部硬约束的候选。V-003 因非冷链且剩余载重仅 400 kg 被排除，V-008 因非冷链被排除，V-011 因剩余载重仅 500 kg 且无在岗司机被排除。

V-005 经 E20 从 N15 到 N04，接驳距离 2.80 km、预计 6 分钟。其载荷率为 `100 / 1000 = 0.10`，评分为：

```text
100 - 6×1.5 - 2.8×2 - 0.10×20 - 0 + 0 + 10 = 93.4
```

车辆故障处理结果为原车辆 V-001 变更为 `BROKEN`，目标车辆 V-005 原子变更为 `RESERVED`，目标司机为 D-003，随后从 N04 继续计算到 N06 的配送路径。

### 8.2 道路堵塞

输入：`新平路东河桥段发生塌方，车辆无法通行。`

结构化结果：

```json
{
  "anomaly_type": "ROAD_BLOCKED",
  "issue_subtype": "LANDSLIDE",
  "affected_edge_id": "E04",
  "road_status": "BLOCKED",
  "order_id": "DEMO-ORDER-005"
}
```

原路线为 E01→E02→E03→E04→E05，总距离 `10.00 km`、基准时间 `20 分钟`。E04 被移除后，Dijkstra 得到 E01→E06→E07→E08→E09，总距离 `13.20 km`、基准时间 `24 分钟`，变化为 `+3.20 km` 和 `+4 分钟`。新路线不得包含 E04。

## 9. 车辆筛选和评分

硬约束按固定顺序执行，并保留所有排除原因：

1. 候选不能是原故障车辆。
2. 车辆状态必须为 `AVAILABLE`。
3. 必须有状态为 `ON_DUTY` 且准驾车型满足要求的司机。
4. `max_load_kg - current_load_kg >= order.cargo_weight_kg`。
5. `COLD_CHAIN` 订单必须由 `COLD_CHAIN` 车辆承运。
6. 车辆重量不得超过接驳和配送路径任一道路的限重。
7. 候选车辆当前位置到异常节点必须存在可通行路径。

合格车辆使用 `FLEET_SCORE_V1`：

```text
score = 100
        - eta_to_incident_minutes × 1.5
        - distance_to_incident_km × 2
        - current_load_ratio × 20
        - road_risk_penalty
        + same_station_bonus
        + cargo_exact_match_bonus
```

- `road_risk_penalty`：低 0、中 6、高 15。
- 候选与异常节点属于同一站点时，`same_station_bonus = 8`，否则为 0。
- 能力与订单类型完全匹配时，`cargo_exact_match_bonus = 10`，否则为 0。
- 分数使用 `Decimal`，量化为 1 位小数。
- 排序依次按得分降序、接驳时间升序、车辆 ID 升序，保证结果可复现。

## 10. Dijkstra 路线计算

路网快照在一次任务内固定版本。`BLOCKED` 边不进入邻接表；`RESTRICTED` 边只有满足车辆重量限制时才能进入邻接表。

分别运行三种目标：

```text
FASTEST edge_weight = base_minutes × congestion_factor
SHORTEST edge_weight = distance_km
SAFEST  edge_weight = base_minutes × congestion_factor + risk_penalty_minutes
```

`risk_penalty_minutes` 为低 0、中 4、高 12。三次结果按边序列去重。

候选路线使用 `ROUTE_SCORE_V1`：

```text
route_score = 100
              - normalized_minutes × 45
              - normalized_distance × 30
              - normalized_risk × 25
```

归一化值按本次候选集合的最大值计算；只有一个候选时，其三个归一化值均按 0 处理。排序依次按路线分数降序、预计分钟升序、距离升序、边 ID 序列字典序。

每个结果包含算法版本、路网版本、访问节点数、节点序列、边序列、总距离、预计时间、累计风险、排除边、目标类型和分项得分。候选路线 ID 固定为 `RTE-` 加 `SHA-256("E01|E06|...")` 前 16 位大写十六进制摘要；相同边序列在任何重试中得到相同 ID。

## 11. 图状态和事件契约

图状态新增：

- `candidate_vehicles`
- `selected_vehicle_id`
- `selected_driver_id`
- `vehicle_reassigned`
- `pickup_route`
- `blocked_edge_ids`
- `original_path`
- `recommended_path`
- `routing_algorithm`
- `road_network_version`
- `distance_delta_km`
- `eta_delta_minutes`
- `road_network_nodes`
- `road_network_edges`

`CAPACITY_COMPLETED` 至少返回原车辆、候选车辆、目标车辆、目标司机、是否换车、选择公式和排除原因。

`ROUTING_COMPLETED` 至少返回阻塞边、原路径、推荐路径、三类候选路径、里程和时间差、访问节点数、算法、路网版本以及用于绘图的路网节点和道路边。

`DISPATCH_COMPLETED` 至少返回原车辆、目标车辆、目标司机、目标路线、状态、版本和是否已执行。

事件 payload 不包含授权头、密钥或连接字符串。

## 12. Result API 与发布

`GET /api/v1/dispatch-tasks/{task_id}/result` 在原有字段之外返回：

- `vehicle_allocation`：原车辆、目标车辆、司机、候选车辆、接驳路线和公式版本。
- `route_plan`：原路径、推荐路径、候选路线、阻塞边、差值、算法、路网版本，以及完整 `network_nodes` 和 `network_edges` 绘图快照。

未发布结果继续遵循现有权限隐藏规则。配送员工只有在主管审核并发布后看到目标车辆、司机、路线和行驶说明；主管可在审核前查看完整计算证据。

## 13. 前端设计

### 13.1 车辆重调度面板

显示原车辆红色故障卡、箭头、目标车辆绿色卡、接驳距离/时间和候选车辆表。候选表同时显示合格与被排除车辆，并显示剩余载重、接驳时间、分项得分和排除原因。

### 13.2 动态路网图

基于 `road_nodes` 的虚拟坐标和 API 路径数据绘制 SVG：

- 普通可用道路为浅灰色。
- 阻塞道路为红色虚线。
- 原路线为灰色粗线。
- 推荐配送路线为绿色粗线。
- 替代车辆接驳路线为蓝色虚线。
- 站点、异常点、起点和终点使用不同图标。

图下方显示原路线与新路线的距离、时间、风险和状态对比，并提供“查看计算过程”折叠区。

### 13.3 Agent 摘要

- 运力 Agent：`扫描 12 辆车，1 辆满足全部约束，选择新物冷链-05。`
- 路径 Agent：`排除 E04，访问节点并生成最快/最短/最安全候选路线。`
- 调度 Agent：`车辆 V-005、司机 D-003 和目标路线已持久化。`
- 审核 Agent：`载重、冷链、司机状态、路径连通性和阻塞边排除校验通过。`

前端在 API 和 mock 模式下使用同一展示组件；mock 数据只能用于纯前端测试，完整 Docker 演示必须使用 API 模式。

## 14. 错误、降级与并发

- `NO_REPLACEMENT_VEHICLE`：无合格替代车辆，进入人工复核。
- `NO_REACHABLE_ROUTE`：堵塞后不存在可达路线，进入人工复核。
- `ROAD_LOCATION_UNRESOLVED`：异常文本不能唯一定位道路，进入人工复核。
- `VEHICLE_RESERVATION_CONFLICT`：目标车辆版本冲突；Worker 在当前候选列表中重新选择下一辆，最多重选一次，再失败则人工复核。
- `ROAD_NETWORK_VERSION_CHANGED`：规划到落库间路网版本改变；重新规划一次，再变化则人工复核。

车辆预占、调度写入和证据写入必须处于同一 MySQL 事务。车辆使用 SQLAlchemy `version_id_col`，`StaleDataError` 转换为领域冲突，不使用 Python 相等比较模拟乐观锁。

Worker 重试继续使用稳定 `task_id` 和 `idempotency_key`。只有终态和调度证据持久化成功后才能 `XACK`，重启不得重复预占车辆或创建调度。

## 15. 测试与验收

实施遵循 TDD：先写行为级失败测试，运行确认失败，完成最小真实实现，再运行通过。

### 15.1 单元测试

- 车辆状态、载重、冷链、司机、道路限重和路径可达性过滤。
- V-005 得分严格等于 `93.4`，并在车辆故障场景被选中。
- 得分相同情况下按接驳时间和车辆 ID 稳定排序。
- Dijkstra 正常路网得到原路径 E01→E02→E03→E04→E05。
- E04 阻塞后得到 E01→E06→E07→E08→E09，且距离 13.20 km、时间 24 分钟。
- `BLOCKED` 边、超限重边和不可达图处理。
- 路线候选去重、综合评分和证据序列化。

### 15.2 集成和并发测试

- MySQL 迁移、全部种子数量、唯一约束和 Decimal 精度。
- 两个任务同时竞争 V-005 时只有一个成功预占，另一个重选或人工复核。
- Redis Streams Worker 完成车辆故障和道路堵塞两条链路。
- Worker 重启、消息重投和 pending recovery 不产生重复调度或重复车辆预占。
- WebSocket 事件和 result API 返回完整车辆与路线证据。

### 15.3 前端和端到端测试

- 候选车辆表显示选中状态和全部排除原因。
- 动态 SVG 正确区分阻塞边、原路线、推荐路线和接驳路线。
- 新旧路线比较显示 `+3.20 km`、`+4 分钟` 和风险下降。
- Playwright 输入车辆故障后验证目标车辆不是 V-001。
- Playwright 输入道路堵塞后验证推荐路线不包含 E04。
- 刷新页面后仍从 MySQL-backed API 读取同一结果。

### 15.4 完成门槛

- `ruff check backend`
- `pytest`
- 前端 lint、test、build
- 针对 MySQL、Redis 的 Docker 集成测试
- 两条场景的浏览器端到端测试
- `git -c safe.directory=<workspace> diff --check`

只记录实际运行过的命令和真实输出，不声称未执行的运行时服务通过验证。
