# CountyFlow 高德真实道路发布与司机端展示设计

**日期：** 2026-09-15

**状态：** 已确认，进入实施

## 1. 目标

修复员工从“我的任务”上报道路异常后，结构化异常位置在异步任务链路中丢失、沙盘上下文加载失败、路线审核以空路径拒绝并最终进入 DLQ 的问题。

调度成功时，发布记录、调度证据和司机端必须引用同一条权威路线。业务订单、司机、车辆和站点继续使用虚拟数据；路线节点固定映射到高德真实地图坐标，并通过高德驾车规划匹配真实道路，使现场演示能看到真实底图、道路折线、起终点、绕行提示、里程和预计时间。

## 2. 已确认根因

1. `AnomalyReportService` 持久化了 `incident_node_id` 和 `affected_edge_id`，但创建调度任务时没有将二者写入 `CreateDispatchTaskRequest`。
2. API 请求、Redis Stream payload 和 Worker 图输入均没有这两个字段，因此 routing Agent 不知道应排除 `E04`。
3. 演示上报来源订单只有名称，没有 `origin_station_id` 和 `destination_station_id`；沙盘仓储只按站点 ID 查找，加载失败后进入旧版固定路线分支。
4. 旧版分支只返回路线标识，不返回节点和边；审核服务对 `ROAD_BLOCKED` 执行连通性检查时拒绝空路径。
5. 当前 `AMap.Driving` 只在车队总览前端临时画线，没有进入调度证据、发布记录或司机任务详情。

`runtime:read` 权限缺失不是调度失败原因。员工角色不应获取 LangGraph 运行态权限，司机页面应隐藏该内部面板。

## 3. 方案

采用“本地安全路径为权威决策，高德真实道路为地理实现”的混合方案：

- 本地 MySQL 路网和 Dijkstra 继续负责确定性排障、车辆重量限制、阻塞边排除和审计。
- 每个虚拟 `road_node_id` 固定映射到高德地图上的真实经纬度；映射版本为 `DEMO_AMAP_V1`。
- routing Agent 选出安全节点序列后，调用窄接口 `RealRoadRouteService.plan(node_ids)`。
- 配置 `AMAP_WEB_SERVICE_KEY` 时，服务端使用高德 Web Service V5 驾车规划并把真实道路折线、距离和时长写入 `ROUTE_CALCULATION` 证据。
- 未配置服务端密钥、超时或高德失败时，在 1 秒内返回 `CLIENT_MATCH_REQUIRED`，保留同一节点序列的真实坐标。该失败不会把一条已通过本地安全验收的演示路线转人工。
- 司机端只在调度已发布后加载高德地图。若后端已有 `AMAP_WEB_SERVICE` 折线，直接绘制该折线；否则使用相同起终点和途经点调用 `AMap.Driving` 匹配真实道路。地图不可用时显示现有本地路线图，不隐藏已发布指令。

## 4. 权威数据流

```text
员工上报 incident_node_id / affected_edge_id
  → FastAPI 校验并写 Redis Stream
  → Worker 恢复完整图输入
  → SandtableContext 按站点 ID 或节点名称定位起终点
  → Dijkstra 排除阻塞边并选择安全节点序列
  → RealRoadRouteService 将节点序列映射为高德真实道路
  → DispatchEvidence 持久化本地路径 + 真实道路结果
  → Audit 审核本地连通性与阻塞边排除
  → Worker 自动发布
  → 司机端读取 publication + 同一份 route_plan
```

必须先完成 `Audit=APPROVED` 和自动发布，Worker 才 `XACK`。发布失败仍保持消息未确认，沿用现有幂等重试规则。

## 5. 契约

### 5.1 异常任务载荷

`CreateDispatchTaskRequest`、`DispatchTaskPayload` 和图输入新增：

- `incident_node_id: str | None`
- `affected_edge_id: str | None`

旧消息没有字段时仍可解析，保证 Redis pending 和 DLQ 兼容。

### 5.2 真实道路证据

`RoutePlanResponse` 新增可空字段 `real_road_route`：

```json
{
  "provider": "AMAP",
  "source": "AMAP_WEB_SERVICE",
  "status": "VERIFIED",
  "coordinate_system": "GCJ02",
  "mapping_version": "DEMO_AMAP_V1",
  "distance_meters": 12640,
  "duration_seconds": 1480,
  "waypoints": [
    {"node_id": "N01", "longitude": "103.044800", "latitude": "25.226500"}
  ],
  "polyline": [
    {"longitude": "103.044800", "latitude": "25.226500"}
  ],
  "fallback_reason": null
}
```

`source` 仅允许：

- `AMAP_WEB_SERVICE`：后端高德返回并通过基础完整性校验的折线。
- `CLIENT_WAYPOINT_FALLBACK`：服务端高德不可用，司机端应使用相同坐标执行道路匹配。

`status` 仅允许 `VERIFIED` 或 `CLIENT_MATCH_REQUIRED`。任何异常文本必须标准化，不包含 URL 查询字符串、Authorization 或高德密钥。

## 6. 自动验收与人工复核边界

本地路线满足以下条件即可继续自动审核和发布：

- 推荐路径至少有两个节点且边序列连续。
- 起终点与订单上下文一致。
- 推荐路径不包含 `affected_edge_id`。
- 每条边满足车辆重量限制。
- 调度证据成功持久化。

高德暂时不可用不触发人工复核，因为业务数据本身为虚拟演示数据，安全约束由本地权威路网验证。只有本地路网确实无可达路径、订单无法定位、车辆约束冲突或持久化冲突时进入人工复核。

## 7. 司机端界面

员工查看已发布任务时，在调度结果上方显示“已发布真实道路路线”卡片：

- 高德深色真实底图和蓝色行驶折线。
- 起点、终点、途经点标记。
- 红色异常/封闭位置提示。
- 路线来源、匹配状态、里程、预计时间和发布时间。
- 高德加载时显示明确进度；失败时显示“已切换本地路线图”。

员工看不到 `RuntimeWorkbench`、LangGraph 检查点和运行态权限错误。主管、调度员和管理员保留现有证据与运行态视图。

## 8. 配置与安全

- 新增 `AMAP_WEB_SERVICE_KEY`，默认空值，仅从环境变量读取。
- 新增 `AMAP_ROUTE_API_BASE_URL=https://restapi.amap.com/v5/direction/driving`。
- 新增 `AMAP_ROUTE_TIMEOUT_SECONDS=0.8`。
- Docker backend/worker 显式透传变量名，不向 frontend 暴露服务端密钥。
- frontend 继续使用 `VITE_AMAP_KEY` 和 `VITE_AMAP_SECURITY_CODE`。
- 日志、错误、事件和 API 响应不得包含任何高德密钥。

## 9. 验收标准

1. 道路封闭上报的 `affected_edge_id=E04` 能贯穿 API、Redis、Worker 和 routing Agent。
2. 演示来源订单即使没有站点 ID，也能按唯一节点名称恢复沙盘上下文。
3. 推荐路径不包含 `E04`，审核为 `APPROVED`，任务不进入 DLQ，自动发布成功。
4. `route_plan.real_road_route` 能从持久化证据恢复，Decimal 坐标以字符串返回。
5. 员工只能在 `publication.status=PUBLISHED` 后看到真实道路地图。
6. 高德服务端失败时任务仍可自动发布；司机端通过 JS API 匹配真实道路，JS API 失败时显示本地路线图。
7. 员工页面不再请求或显示 RuntimeWorkbench。
8. 后端 lint/pytest、前端 lint/test/build、Docker 定向集成测试和 `git diff --check` 通过。

