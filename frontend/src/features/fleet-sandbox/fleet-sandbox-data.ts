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
  { id: "N01", name: "杨林中心仓", x: 517, y: 344, kind: "HUB" },
  { id: "N02", name: "西环路口", x: 447, y: 323, kind: "JUNCTION" },
  { id: "N03", name: "园区西路口", x: 584, y: 295, kind: "JUNCTION" },
  { id: "N04", name: "故障上报点", x: 704, y: 268, kind: "JUNCTION" },
  { id: "N05", name: "东环路口", x: 840, y: 245, kind: "JUNCTION" },
  { id: "N06", name: "城东配送站", x: 1009, y: 210, kind: "STATION" },
  { id: "N07", name: "南环西口", x: 371, y: 420, kind: "JUNCTION" },
  { id: "N08", name: "南环中段", x: 611, y: 455, kind: "JUNCTION" },
  { id: "N09", name: "南环东口", x: 845, y: 392, kind: "JUNCTION" },
  { id: "N10", name: "北部园区路口", x: 409, y: 187, kind: "JUNCTION" },
  { id: "N11", name: "北部乡镇驿站", x: 344, y: 47, kind: "SERVICE" },
  { id: "N12", name: "河西综合服务站", x: 125, y: 264, kind: "SERVICE" },
  { id: "N13", name: "南部村镇服务点", x: 665, y: 610, kind: "SERVICE" },
  { id: "N14", name: "冷链物流中心", x: 224, y: 381, kind: "STATION" },
  { id: "N15", name: "县域车辆维修站", x: 693, y: 338, kind: "STATION" },
  { id: "N16", name: "农资配送路口", x: 256, y: 140, kind: "JUNCTION" },
  { id: "N17", name: "城北电商服务点", x: 993, y: 85, kind: "SERVICE" },
  { id: "N18", name: "东南末端服务站", x: 1096, y: 431, kind: "SERVICE" },
  { id: "N19", name: "智慧物流调度中心", x: 551, y: 369, kind: "HUB" },
  { id: "N20", name: "快递集散站", x: 775, y: 311, kind: "STATION" },
  { id: "N21", name: "新能源车辆充电站", x: 911, y: 350, kind: "STATION" },
  { id: "N22", name: "应急救援站", x: 649, y: 326, kind: "STATION" },
];

export const fleetEdges: FleetMapEdge[] = [
  { id: "E01", from: "N19", to: "N01" }, { id: "E02", from: "N01", to: "N02" },
  { id: "E03", from: "N01", to: "N03" }, { id: "E04", from: "N03", to: "N04" },
  { id: "E05", from: "N04", to: "N05" }, { id: "E06", from: "N05", to: "N06" },
  { id: "E07", from: "N02", to: "N07" }, { id: "E08", from: "N07", to: "N08" },
  { id: "E09", from: "N08", to: "N09" }, { id: "E10", from: "N09", to: "N06" },
  { id: "E11", from: "N01", to: "N10" }, { id: "E12", from: "N10", to: "N16" },
  { id: "E13", from: "N16", to: "N11" }, { id: "E14", from: "N16", to: "N12" },
  { id: "E15", from: "N08", to: "N13" }, { id: "E16", from: "N14", to: "N07" },
  { id: "E17", from: "N05", to: "N17" }, { id: "E18", from: "N11", to: "N17" },
  { id: "E19", from: "N09", to: "N18" }, { id: "E20", from: "N15", to: "N04" },
  { id: "E21", from: "N15", to: "N19" }, { id: "E22", from: "N03", to: "N22" },
  { id: "E23", from: "N22", to: "N20" }, { id: "E24", from: "N20", to: "N05" },
  { id: "E25", from: "N09", to: "N21" }, { id: "E26", from: "N21", to: "N18" },
  { id: "E27", from: "N19", to: "N20" }, { id: "E28", from: "N20", to: "N21" },
  { id: "E29", from: "N21", to: "N15" }, { id: "E30", from: "N02", to: "N16" },
  { id: "E31", from: "N03", to: "N10" }, { id: "E32", from: "N17", to: "N06" },
  { id: "E33", from: "N04", to: "N20" },
];

export const fleetRoutes: FleetRoute[] = [
  { id: "ROUTE-01", displayId: "路线-01", name: "调度中心—快递集散线", nodeIds: ["N19", "N01", "N03", "N22", "N20", "N05", "N06"], color: "#287f75", labelX: 760, labelY: 195 },
  { id: "ROUTE-02", displayId: "路线-02", name: "南环快速配送线", nodeIds: ["N19", "N01", "N02", "N07", "N08", "N09", "N21", "N18"], color: "#3f6fb5", labelX: 730, labelY: 505 },
  { id: "ROUTE-03", displayId: "路线-03", name: "北部乡镇配送线", nodeIds: ["N19", "N01", "N10", "N16", "N11", "N17"], color: "#8a62a9", labelX: 520, labelY: 42 },
  { id: "ROUTE-04", displayId: "路线-04", name: "河西农资配送线", nodeIds: ["N19", "N01", "N02", "N16", "N12"], color: "#9b6b2f", labelX: 175, labelY: 110 },
  { id: "ROUTE-05", displayId: "路线-05", name: "南部村镇支线", nodeIds: ["N19", "N01", "N02", "N07", "N08", "N13"], color: "#b05c75", labelX: 720, labelY: 642 },
  { id: "ROUTE-06", displayId: "路线-06", name: "冷链物流专线", nodeIds: ["N14", "N07", "N02", "N01", "N19", "N20"], color: "#2581a2", labelX: 250, labelY: 470 },
  { id: "ROUTE-07", displayId: "路线-07", name: "东南末端配送线", nodeIds: ["N19", "N20", "N21", "N18"], color: "#57813b", labelX: 970, labelY: 470 },
  { id: "ROUTE-08", displayId: "路线-08", name: "城北电商配送线", nodeIds: ["N19", "N01", "N03", "N10", "N16", "N11", "N17"], color: "#8a7142", labelX: 900, labelY: 120 },
  { id: "ROUTE-09", displayId: "路线-09", name: "园区综合环线", nodeIds: ["N19", "N20", "N05", "N06", "N17", "N11", "N16", "N10", "N01"], color: "#4d6991", labelX: 795, labelY: 75 },
  { id: "ROUTE-10", displayId: "路线-10", name: "维修救援接驳线", nodeIds: ["N22", "N03", "N04", "N15", "N19", "N20"], color: "#b24d43", labelX: 630, labelY: 410 },
];

export const fleetRoadLabels: FleetRoadLabel[] = [
  { id: "ROAD-01", name: "杨林大道", x: 720, y: 270 },
  { id: "ROAD-02", name: "南环路", x: 675, y: 488 },
  { id: "ROAD-03", name: "嵩玉线", x: 350, y: 145, rotate: -45 },
  { id: "ROAD-04", name: "空港东路", x: 935, y: 325, rotate: -32 },
  { id: "ROAD-05", name: "农资配送路", x: 215, y: 205, rotate: -18 },
  { id: "ROAD-06", name: "村镇服务路", x: 690, y: 560, rotate: 42 },
  { id: "ROAD-07", name: "物流园联络线", x: 610, y: 350, rotate: -12 },
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
