import type { DashboardSnapshot, DispatchDetail } from "../types/dispatch";
import type { RoutePlanResponse } from "../services/api/dispatch-adapter";

export const dashboardSnapshot: DashboardSnapshot = {
  metrics: [
    { label: "今日运单", value: "1,284", note: "较昨日 +8.4%" },
    { label: "配送中", value: "863", note: "67.2% 正在执行", tone: "teal" },
    { label: "当前异常", value: "17", note: "4 项需人工关注", tone: "amber" },
    { label: "AI 自动解决率", value: "91.8%", note: "近 7 日均值", tone: "violet" },
    { label: "准时配送率", value: "96.8%", note: "目标 95.0%", tone: "teal" },
    { label: "Worker", value: "3 / 3", note: "全部在线", tone: "teal" },
  ],
  recentAnomalies: [
    { id: "ANM-20260821-017", taskId: "TASK-20260821-0042", orderId: "CF-20260821-00128", type: "暴雨道路湿滑", risk: "HIGH", driver: "李师傅", route: "新平路", status: "已完成调度", occurredAt: "20:04" },
    { id: "ANM-20260821-016", taskId: "TASK-20260821-0041", orderId: "CF-20260821-00127", type: "道路封闭", risk: "HIGH", driver: "王师傅", route: "东河乡道", status: "处理中", occurredAt: "19:42" },
    { id: "ANM-20260821-015", taskId: "TASK-20260821-0040", orderId: "CF-20260821-00126", type: "车辆故障", risk: "MEDIUM", driver: "张师傅", route: "城北物流线", status: "已完成调度", occurredAt: "19:18" },
    { id: "ANM-20260821-014", taskId: "TASK-20260821-0039", orderId: "CF-20260821-00124", type: "站点积压", risk: "MEDIUM", driver: "刘师傅", route: "308县道", status: "人工复核", occurredAt: "18:56" },
    { id: "ANM-20260821-013", taskId: "TASK-20260821-0038", orderId: "CF-20260821-00123", type: "运力不足", risk: "LOW", driver: "王师傅", route: "102国道", status: "已完成调度", occurredAt: "18:31" },
  ],
  agents: [
    { id: "intake", name: "接入", status: "SUCCESS", elapsed: "12 毫秒", output: "异常上下文已规范化" },
    { id: "memory", name: "实体记忆", status: "SUCCESS", elapsed: "42 毫秒", output: "memory-rain-li" },
    { id: "graph_memory", name: "图记忆", status: "SUCCESS", elapsed: "18 毫秒", output: "3 条图事实" },
    { id: "environment", name: "环境", status: "FALLBACK", elapsed: "811 毫秒", output: "静态路线规则", detail: "主要服务超时" },
    { id: "capacity", name: "运力", status: "SUCCESS", elapsed: "18 毫秒", output: "可用" },
    { id: "routing", name: "路径规划", status: "SUCCESS", elapsed: "31 毫秒", output: "national-102" },
    { id: "dispatch", name: "调度", status: "SUCCESS", elapsed: "27 毫秒", output: "已执行改道" },
    { id: "audit", name: "审核", status: "APPROVED", elapsed: "14 毫秒", output: "调度完成" },
  ],
};

export const mockRoutePlan: RoutePlanResponse = {
  original_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N04", "N06"], edge_ids: ["E01", "E04", "E05"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "1.00", visited_node_count: 6, scoring_formula: null },
  recommended_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"], edge_ids: ["E01", "E06", "E07", "E08", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0.30", visited_node_count: 8, scoring_formula: "ROUTE_SCORE_V1" },
  candidate_routes: [{ route_id: "RTE-DEMO-NORTH", route_name: "北环绕行线", objective: "FASTEST", node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"], edge_ids: ["E01", "E06", "E07", "E08", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_level: "LOW", risk_cost: "0.30", visited_node_count: 8, available: true, reason: null, score: "92.00", score_components: null, scoring_formula: "ROUTE_SCORE_V1", algorithm_version: "DIJKSTRA_V1", road_network_version: 7 }],
  blocked_edge_ids: ["E04"],
  distance_delta_km: "3.20",
  eta_delta_minutes: 4,
  visited_node_count: 8,
  routing_status: "ROUTED",
  algorithm: "DIJKSTRA_V1",
  road_network_version: 7,
  network_nodes: [
    { node_id: "N01", name: "中心仓", x_km: "0.00", y_km: "2.00", node_type: "DEPOT" },
    { node_id: "N02", name: "北门", x_km: "2.00", y_km: "2.00", node_type: "JUNCTION" },
    { node_id: "N04", name: "东河桥", x_km: "6.00", y_km: "2.00", node_type: "JUNCTION" },
    { node_id: "N06", name: "城东站", x_km: "10.00", y_km: "2.00", node_type: "STATION" },
    { node_id: "N07", name: "北环一口", x_km: "3.00", y_km: "5.00", node_type: "JUNCTION" },
    { node_id: "N08", name: "北环二口", x_km: "5.00", y_km: "6.00", node_type: "JUNCTION" },
    { node_id: "N09", name: "北环三口", x_km: "8.00", y_km: "5.00", node_type: "JUNCTION" },
  ],
  network_edges: [
    { edge_id: "E01", name: "仓前路", from_node_id: "N01", to_node_id: "N02", distance_km: "2.00", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E04", name: "新平路东河桥段", from_node_id: "N02", to_node_id: "N04", distance_km: "5.00", base_minutes: 10, road_level: "COUNTY", risk_level: "HIGH", status: "BLOCKED", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E05", name: "新平路东段", from_node_id: "N04", to_node_id: "N06", distance_km: "3.00", base_minutes: 6, road_level: "COUNTY", risk_level: "MEDIUM", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E06", name: "北环入口", from_node_id: "N02", to_node_id: "N07", distance_km: "2.60", base_minutes: 5, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E07", name: "北环支路", from_node_id: "N07", to_node_id: "N08", distance_km: "2.40", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E08", name: "北环东段", from_node_id: "N08", to_node_id: "N09", distance_km: "3.20", base_minutes: 6, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
    { edge_id: "E09", name: "城东联络线", from_node_id: "N09", to_node_id: "N06", distance_km: "3.00", base_minutes: 5, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
  ],
};

export const dispatchDetail: DispatchDetail = {
  taskId: "TASK-20260821-0042", orderId: "CF-20260821-00128", driver: "李师傅", vehicle: "苏G·A8126", originalRoute: "新平路", anomaly: "暴雨道路湿滑", severity: "HIGH", status: "COMPLETED",
  description: "李师傅在雨天经过新平路，道路出现湿滑风险，需要选择更安全的路线。",
  candidates: [
    { id: "national-102", label: "102国道", distance: "13.0 公里", eta: "24 分钟", risk: "LOW", score: 92, state: "RECOMMENDED" },
    { id: "county-308", label: "308县道", distance: "15.0 公里", eta: "28 分钟", risk: "MEDIUM", score: 74 },
    { id: "xinping-road", label: "新平路", distance: "10.0 公里", eta: "18 分钟", risk: "HIGH", score: 31, state: "UNAVAILABLE", reason: "暴雨条件下道路湿滑风险高" },
  ],
  memory: { memoryId: "memory-rain-li", driver: "李师傅", route: "新平路", anomaly: "雨天道路湿滑", resolution: "建议改走102国道", similarity: "94.6%", adopted: true },
  graphMemory: {
    used: true,
    entities: ["李师傅", "新平路", "雨天", "102国道"],
    facts: ["李师傅 → HAS_RISK_ON → 新平路", "102国道 → ALTERNATIVE_TO → 新平路"],
    paths: ["李师傅 → 新平路 → 雨天"],
  },
  environment: { weather: "暴雨", road: "道路湿滑", risk: "HIGH", provider: "超时", timeout: "0.8 秒", fallback: "静态路线规则", elapsed: "811 毫秒", circuit: "关闭" },
  capacity: { driver: "可用", vehicle: "可用", vehicleLoad: 45, stationLoad: 60, status: "AVAILABLE", risk: "LOW" },
  decisionReason: "当前新平路在暴雨条件下存在道路湿滑高风险。系统召回历史记录 memory-rain-li，相似度 94.6%，历史处理方案为“建议改走102国道”。当前司机及车辆运力状态为可用。综合历史经验、环境风险及运力状态，系统推荐改走102国道。",
  agents: dashboardSnapshot.agents,
  dispatch: { decision: "改道", originalRoute: "xinping-road", targetRoute: "national-102", executed: true, version: 1, memoryAdopted: true, fallbackUsed: true },
  audit: { status: "APPROVED", checks: ["路线一致性", "记忆证据", "降级记录", "调度已持久化"] },
};
