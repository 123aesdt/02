import { fleetEdges, fleetNodes, fleetVehicles } from "./fleet-sandbox-data";
import type { VehicleOperationSnapshot } from "../../types/vehicle-operations";


const edgeNames: Record<string, string> = {
  E01: "中心仓连接线", E02: "西环至新平路", E03: "新平路西段", E04: "新平路东河桥段",
  E05: "东河桥连接线", E06: "102 国道引道", E07: "102 国道西段", E08: "102 国道东段",
  E09: "国道至城东站", E20: "维修站接驳线", E21: "维修站国道线",
};

export const demoVehicleOperationSnapshot: VehicleOperationSnapshot = {
  task_id: "DEMO-TASK-REPORT-VEHICLE",
  generated_at: "2026-09-10T18:42:00+08:00",
  incident: {
    status: "AUTO_PROCESSING",
    risk: "HIGH",
    vehicle_id: "V-001",
    replacement_vehicle_id: "V-005",
    location_node_id: "N04",
    fault_code: "ENGINE_COOLING",
    cargo: "冷链生鲜 · 700kg",
  },
  nodes: fleetNodes.map((node) => ({
    node_id: node.id,
    name: node.name,
    x_km: String(node.x / 100),
    y_km: String((680 - node.y) / 100),
    node_type: node.kind,
  })),
  edges: fleetEdges.map((edge) => ({
    edge_id: edge.id,
    name: edgeNames[edge.id] ?? `县域道路 ${edge.id}`,
    from_node_id: edge.from,
    to_node_id: edge.to,
    road_level: ["E07", "E08"].includes(edge.id) ? "NATIONAL" : "COUNTY",
    status: "OPEN",
  })),
  vehicles: fleetVehicles.map((vehicle) => ({
    vehicle_id: vehicle.id,
    plate_no: vehicle.id === "V-001" ? "新物冷链-01" : vehicle.id === "V-005" ? "新物冷链-05" : `新物车辆-${vehicle.id.slice(-2)}`,
    status: vehicle.id === "V-001" ? "WAITING_RESCUE" : vehicle.id === "V-005" ? "IN_TRANSIT" : vehicle.status,
    current_node_id: vehicle.id === "V-001" ? "N04" : vehicle.id === "V-005" ? "N15" : fleetNodes[vehicle.initialStep % fleetNodes.length].id,
    is_incident: vehicle.id === "V-001",
    is_replacement: vehicle.id === "V-005",
  })),
  routes: [
    { kind: "REPLACEMENT", edge_ids: ["E21", "E03", "E04"], node_ids: ["N15", "N19", "N01", "N03", "N04"], status: "ACTIVE" },
    { kind: "RESCUE", edge_ids: ["E22", "E04"], node_ids: ["N22", "N03", "N04"], status: "ARRIVED" },
    { kind: "TOW", edge_ids: ["E20"], node_ids: ["N04", "N15"], status: "WAITING" },
    { kind: "INTERRUPTED", edge_ids: ["E04"], node_ids: ["N03", "N04"], status: "INTERRUPTED" },
  ],
  rescue: {
    mission_no: "JY-20260910-002",
    status: "ARRIVED",
    progress_percent: 41,
    rescue_unit_id: "救援-02",
    incident_node_id: "N04",
    station_node_id: "N15",
    next_transition_at: null,
  },
  maintenance: {
    order_no: "WX-20260910-018",
    vehicle_id: "V-001",
    bay_code: "A-02",
    status: "REPAIRING",
    fault_code: "ENGINE_COOLING",
    diagnosis: "发动机冷却系统故障",
    repair_minutes: 120,
    manual_inspection_required: false,
    inspection_result: null,
    progress_percent: 41,
    countdown_seconds: 58,
    available_after: "2026-09-10T20:42:00+08:00",
  },
  stages: [
    { key: "SAFE_STOP", title: "安全停车", status: "COMPLETED", detail: "停车确认、冷链保温与道路警示已完成" },
    { key: "REPLACEMENT", title: "替代配送接管", status: "COMPLETED", detail: "新物冷链-05 · 陈师傅 · 接驳路线已下发" },
    { key: "RESCUE", title: "救援运送", status: "ACTIVE", detail: "救援-02 前往故障点，随后运往县域维修站" },
    { key: "MAINTENANCE", title: "维修与自动复岗", status: "WAITING", detail: "工位已预留；维修结束后自动触发安全检查" },
  ],
  timeline: [
    { event_id: "1", event_type: "VEHICLE_STOPPED", label: "发现故障", timestamp: "18:42", payload: {} },
    { event_id: "2", event_type: "REPLACEMENT_DISPATCHED", label: "自动决策", timestamp: "18:43", payload: {} },
    { event_id: "3", event_type: "MAINTENANCE_REPAIRING", label: "运往维修站", timestamp: "18:51", payload: {} },
    { event_id: "4", event_type: "VEHICLE_AVAILABLE", label: "预计自动复岗", timestamp: "20:42", payload: {} },
  ],
};
