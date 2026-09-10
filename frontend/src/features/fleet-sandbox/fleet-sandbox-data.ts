import type { AnomalyListItem } from "../../types/workspace-read-models";

export type FleetVehicleStatus = "IN_TRANSIT" | "AVAILABLE" | "DISPATCHING" | "BROKEN" | "MAINTENANCE";

export interface FleetMapNode {
  id: string;
  name: string;
  x: number;
  y: number;
  kind: "HUB" | "STATION" | "JUNCTION" | "SERVICE";
}

export interface FleetMapEdge {
  id: string;
  from: string;
  to: string;
}

export interface FleetRoute {
  id: string;
  displayId: string;
  name: string;
  nodeIds: string[];
  color: string;
  labelX: number;
  labelY: number;
}

export interface FleetRoadLabel {
  id: string;
  name: string;
  x: number;
  y: number;
  rotate?: number;
}

export interface FleetVehicle {
  id: string;
  routeId: string;
  status: FleetVehicleStatus;
  initialStep: number;
  speedKph: number;
  loadKg: number;
  capacityKg: number;
}

export const fleetNodes: FleetMapNode[] = [
  { id: "N01", name: "新平县中心仓", x: 500, y: 325, kind: "HUB" },
  { id: "N02", name: "西环路口", x: 390, y: 330, kind: "JUNCTION" },
  { id: "N03", name: "新平路西口", x: 530, y: 245, kind: "JUNCTION" },
  { id: "N04", name: "新平路 K3.2", x: 680, y: 235, kind: "JUNCTION" },
  { id: "N05", name: "东河桥", x: 845, y: 250, kind: "JUNCTION" },
  { id: "N06", name: "城东配送站", x: 1035, y: 275, kind: "STATION" },
  { id: "N07", name: "102 国道西口", x: 410, y: 450, kind: "JUNCTION" },
  { id: "N08", name: "102 国道中段", x: 640, y: 465, kind: "JUNCTION" },
  { id: "N09", name: "102 国道东口", x: 865, y: 415, kind: "JUNCTION" },
  { id: "N10", name: "308 县道口", x: 365, y: 190, kind: "JUNCTION" },
  { id: "N11", name: "北岭村驿站", x: 455, y: 80, kind: "SERVICE" },
  { id: "N12", name: "河西乡服务站", x: 125, y: 250, kind: "SERVICE" },
  { id: "N13", name: "南山村服务点", x: 760, y: 600, kind: "SERVICE" },
  { id: "N14", name: "新平冷链中心", x: 255, y: 405, kind: "STATION" },
  { id: "N15", name: "县域车辆维修站", x: 670, y: 335, kind: "STATION" },
  { id: "N16", name: "河西农资路口", x: 235, y: 145, kind: "JUNCTION" },
  { id: "N17", name: "城东电商服务点", x: 1015, y: 115, kind: "SERVICE" },
  { id: "N18", name: "双河村路口", x: 1080, y: 455, kind: "SERVICE" },
];

export const fleetEdges: FleetMapEdge[] = [
  { id: "E01", from: "N01", to: "N02" }, { id: "E02", from: "N02", to: "N03" },
  { id: "E03", from: "N03", to: "N04" }, { id: "E04", from: "N04", to: "N05" },
  { id: "E05", from: "N05", to: "N06" }, { id: "E06", from: "N02", to: "N07" },
  { id: "E07", from: "N07", to: "N08" }, { id: "E08", from: "N08", to: "N09" },
  { id: "E09", from: "N09", to: "N06" }, { id: "E10", from: "N01", to: "N10" },
  { id: "E11", from: "N10", to: "N11" }, { id: "E12", from: "N10", to: "N16" },
  { id: "E13", from: "N16", to: "N12" }, { id: "E14", from: "N08", to: "N13" },
  { id: "E15", from: "N14", to: "N01" }, { id: "E16", from: "N05", to: "N17" },
  { id: "E17", from: "N06", to: "N17" }, { id: "E18", from: "N09", to: "N18" },
  { id: "E19", from: "N06", to: "N18" }, { id: "E20", from: "N15", to: "N04" },
  { id: "E21", from: "N15", to: "N01" }, { id: "E22", from: "N12", to: "N02" },
  { id: "E23", from: "N11", to: "N17" }, { id: "E24", from: "N13", to: "N18" },
  { id: "E25", from: "N03", to: "N10" }, { id: "E26", from: "N05", to: "N09" },
];

export const fleetRoutes: FleetRoute[] = [
  { id: "ROUTE-01", displayId: "路线-01", name: "中心仓—城东配送线", nodeIds: ["N01", "N02", "N03", "N04", "N05", "N06"], color: "#287f75", labelX: 715, labelY: 198 },
  { id: "ROUTE-02", displayId: "路线-02", name: "102 国道快速线", nodeIds: ["N01", "N02", "N07", "N08", "N09", "N06"], color: "#3f6fb5", labelX: 700, labelY: 520 },
  { id: "ROUTE-03", displayId: "路线-03", name: "北岭村山区线", nodeIds: ["N01", "N10", "N11"], color: "#8a62a9", labelX: 420, labelY: 48 },
  { id: "ROUTE-04", displayId: "路线-04", name: "河西农资配送线", nodeIds: ["N01", "N10", "N16", "N12"], color: "#9b6b2f", labelX: 120, labelY: 105 },
  { id: "ROUTE-05", displayId: "路线-05", name: "南山村支线", nodeIds: ["N01", "N02", "N07", "N08", "N13"], color: "#b05c75", labelX: 780, labelY: 642 },
  { id: "ROUTE-06", displayId: "路线-06", name: "新平冷链专线", nodeIds: ["N14", "N01", "N02", "N07", "N08"], color: "#2581a2", labelX: 205, labelY: 468 },
  { id: "ROUTE-07", displayId: "路线-07", name: "双河村末端配送线", nodeIds: ["N01", "N02", "N07", "N08", "N09", "N18"], color: "#57813b", labelX: 955, labelY: 545 },
  { id: "ROUTE-08", displayId: "路线-08", name: "东河桥常规线", nodeIds: ["N01", "N02", "N03", "N04", "N05", "N17"], color: "#8a7142", labelX: 875, labelY: 175 },
  { id: "ROUTE-09", displayId: "路线-09", name: "城北驿站环线", nodeIds: ["N01", "N10", "N11", "N17", "N06", "N09", "N08", "N07", "N02"], color: "#4d6991", labelX: 745, labelY: 76 },
  { id: "ROUTE-10", displayId: "路线-10", name: "维修救援接驳线", nodeIds: ["N15", "N04", "N03", "N02", "N07", "N08"], color: "#b24d43", labelX: 550, labelY: 405 },
];

export const fleetRoadLabels: FleetRoadLabel[] = [
  { id: "ROAD-01", name: "新平路", x: 690, y: 270 },
  { id: "ROAD-02", name: "102 国道", x: 660, y: 495 },
  { id: "ROAD-03", name: "308 县道", x: 335, y: 135, rotate: -48 },
  { id: "ROAD-04", name: "东河桥连接线", x: 915, y: 360, rotate: -35 },
  { id: "ROAD-05", name: "河西农资路", x: 210, y: 195, rotate: -22 },
  { id: "ROAD-06", name: "南山村道", x: 720, y: 555, rotate: 48 },
  { id: "ROAD-07", name: "双河村道", x: 1005, y: 485, rotate: 18 },
];

const statuses: FleetVehicleStatus[] = [
  "IN_TRANSIT", "IN_TRANSIT", "AVAILABLE", "AVAILABLE", "AVAILABLE",
  "IN_TRANSIT", "MAINTENANCE", "IN_TRANSIT", "BROKEN", "AVAILABLE",
  "IN_TRANSIT", "BROKEN", "AVAILABLE", "IN_TRANSIT", "DISPATCHING",
  "AVAILABLE", "IN_TRANSIT", "MAINTENANCE", "DISPATCHING", "IN_TRANSIT",
];

export const fleetVehicles: FleetVehicle[] = Array.from({ length: 20 }, (_, index) => ({
  id: `V-${String(index + 1).padStart(3, "0")}`,
  routeId: `ROUTE-${String(Math.floor(index / 2) + 1).padStart(2, "0")}`,
  status: statuses[index],
  initialStep: index % 5,
  speedKph: statuses[index] === "IN_TRANSIT" ? 34 + (index % 5) * 4 : statuses[index] === "DISPATCHING" ? 46 : 0,
  loadKg: statuses[index] === "MAINTENANCE" || statuses[index] === "BROKEN" ? 0 : 280 + (index % 8) * 95,
  capacityKg: 1200,
}));

export const fleetStatusMeta: Record<FleetVehicleStatus, { label: string; color: string }> = {
  IN_TRANSIT: { label: "行驶中", color: "#2f8a5b" },
  AVAILABLE: { label: "空闲", color: "#3478b9" },
  DISPATCHING: { label: "调度中", color: "#d88428" },
  BROKEN: { label: "故障", color: "#c84b4b" },
  MAINTENANCE: { label: "维修中", color: "#7a8491" },
};

const anomalyTypeLabels: Record<string, string> = {
  VEHICLE_BREAKDOWN: "车辆故障-01",
  ROAD_BLOCKED: "道路堵塞-02",
  WEATHER_RISK: "天气风险-03",
  CAPACITY_SHORTAGE: "运力不足-04",
  DELIVERY_DELAY: "配送延误-05",
};

const anomalyStatusLabels: Record<string, string> = {
  REPORTED: "已上报-01",
  PENDING: "已上报-01",
  RUNNING: "处理中-02",
  PROCESSING: "处理中-02",
  COMPLETED: "调度完成-03",
  REVIEW_REQUIRED: "等待复核-04",
  NEEDS_REVIEW: "等待复核-04",
  FAILED: "等待复核-04",
};

function sequence(value: number): string {
  return String(value).padStart(3, "0");
}

function numericSuffix(value: string | null | undefined, fallback: number): string {
  const match = value?.match(/(\d+)(?!.*\d)/);
  return sequence(match ? Number(match[1]) : fallback);
}

export function vehicleDisplayLabel(vehicleId: string | null | undefined): string {
  return `车辆-${numericSuffix(vehicleId, 0)}`;
}

export function reportSourceDisplayLabel(
  vehicleId: string | null | undefined,
  orderNo: string | null | undefined,
): string {
  const vehicleSequence = Number(numericSuffix(vehicleId, 0));
  return `配送任务-${sequence(vehicleSequence)}｜运单-${numericSuffix(orderNo, vehicleSequence)}`;
}

export function anomalyReferenceLabel(anomalyId: number, anomalyNo: string | null | undefined): string {
  return `异常-${numericSuffix(anomalyNo, anomalyId)}`;
}

export function dispatchTaskReferenceLabel(taskId: string | null | undefined, fallback: number): string {
  return `调度任务-${numericSuffix(taskId, fallback)}`;
}

export function problemTypeLabel(value: string | null | undefined): string {
  return anomalyTypeLabels[value?.trim().toUpperCase() ?? ""] ?? "其他异常-99";
}

export function taskStatusLabel(value: string | null | undefined): string {
  return anomalyStatusLabels[value?.trim().toUpperCase() ?? ""] ?? "状态未知-99";
}

export function anomalyDisplayLabel(anomaly: AnomalyListItem): string {
  const row = sequence(anomaly.row_id);
  const order = numericSuffix(anomaly.order_no, anomaly.row_id);
  return `异常-${row}｜运单-${order}｜${problemTypeLabel(anomaly.anomaly_type)}｜${taskStatusLabel(anomaly.status)}｜调度任务-${row}`;
}

export function taskDisplayId(sequenceNumber: number): string {
  return `调度任务-${sequence(sequenceNumber)}`;
}
