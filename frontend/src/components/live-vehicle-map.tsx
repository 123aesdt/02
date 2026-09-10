import { Pause, Play, Radio, RotateCcw, Truck } from "lucide-react";
import { useEffect, useState } from "react";

import type { PathResponse, RoadEdgeResponse, RoadNodeResponse, RoutePlanResponse, VehicleAllocationResponse } from "../services/api/dispatch-adapter";
import type { TaskEvent } from "../types/task-events";
import { RouteVisual, type RouteVehicleMarker } from "./route-visual";

interface LiveVehicleMapProps {
  anomalyType: string | null | undefined;
  allocation: VehicleAllocationResponse | null | undefined;
  routePlan: RoutePlanResponse | null | undefined;
  connection: "CONNECTED" | "RECONNECTING" | "DISCONNECTED";
  events?: TaskEvent[];
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function pathFromEvent(value: unknown): PathResponse | null {
  const source = record(value);
  if (!source) return null;
  const nodeIds = stringList(source.node_ids);
  const edgeIds = stringList(source.edge_ids);
  if (!nodeIds.length) return null;
  return {
    objective: text(source.objective) ?? "FASTEST",
    node_ids: nodeIds,
    edge_ids: edgeIds,
    distance_km: text(source.distance_km) ?? "0.00",
    estimated_minutes: numberValue(source.estimated_minutes) ?? 0,
    risk_cost: text(source.risk_cost) ?? "0.00",
    visited_node_count: numberValue(source.visited_node_count) ?? nodeIds.length,
    scoring_formula: text(source.scoring_formula),
  };
}

function roadNodesFromEvent(value: unknown): RoadNodeResponse[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const source = record(item);
    const nodeId = text(source?.node_id);
    const x = text(source?.x_km);
    const y = text(source?.y_km);
    if (!source || !nodeId || !x || !y) return [];
    return [{ node_id: nodeId, name: text(source.name) ?? nodeId, x_km: x, y_km: y, node_type: text(source.node_type) ?? "JUNCTION" }];
  });
}

function roadEdgesFromEvent(value: unknown): RoadEdgeResponse[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const source = record(item);
    const edgeId = text(source?.edge_id);
    const fromNodeId = text(source?.from_node_id);
    const toNodeId = text(source?.to_node_id);
    if (!source || !edgeId || !fromNodeId || !toNodeId) return [];
    return [{
      edge_id: edgeId,
      name: text(source.name) ?? edgeId,
      from_node_id: fromNodeId,
      to_node_id: toNodeId,
      distance_km: text(source.distance_km) ?? "0.00",
      base_minutes: numberValue(source.base_minutes) ?? 0,
      road_level: text(source.road_level) ?? "COUNTY",
      risk_level: text(source.risk_level) ?? "LOW",
      status: text(source.status) ?? "OPEN",
      congestion_factor: text(source.congestion_factor) ?? "1.00",
      weight_limit_tons: text(source.weight_limit_tons) ?? "0.00",
      bidirectional: typeof source.bidirectional === "boolean" ? source.bidirectional : true,
      version: numberValue(source.version) ?? 0,
    }];
  });
}

function routePlanFromEvents(events: TaskEvent[]): RoutePlanResponse | null {
  const source = events.filter((event) => event.event_type === "ROUTING_COMPLETED").at(-1)?.data;
  if (!source) return null;
  const networkNodes = roadNodesFromEvent(source.network_nodes);
  const networkEdges = roadEdgesFromEvent(source.network_edges);
  if (!networkNodes.length || !networkEdges.length) return null;
  const recommendedPath = pathFromEvent(source.recommended_path);
  return {
    original_path: pathFromEvent(source.original_path),
    recommended_path: recommendedPath,
    candidate_routes: [],
    blocked_edge_ids: stringList(source.blocked_edge_ids),
    distance_delta_km: text(source.distance_delta_km),
    eta_delta_minutes: numberValue(source.eta_delta_minutes),
    visited_node_count: numberValue(source.visited_node_count) ?? recommendedPath?.visited_node_count ?? null,
    routing_status: text(source.routing_status),
    algorithm: text(source.algorithm) ?? "DIJKSTRA_V1",
    road_network_version: numberValue(source.road_network_version),
    network_nodes: networkNodes,
    network_edges: networkEdges,
  };
}

function capacityEventData(events: TaskEvent[]): Record<string, unknown> {
  return events.filter((event) => event.event_type === "CAPACITY_COMPLETED").at(-1)?.data ?? {};
}

function connectionCopy(connection: LiveVehicleMapProps["connection"]): string {
  if (connection === "CONNECTED") return "实时事件已连接";
  if (connection === "RECONNECTING") return "实时事件重连中";
  return "实时事件未连接";
}

export function LiveVehicleMap({ anomalyType, allocation, routePlan, connection, events = [] }: LiveVehicleMapProps) {
  const capacityData = capacityEventData(events);
  const effectiveRoutePlan = routePlan ?? routePlanFromEvents(events);
  const originalVehicleId = text(capacityData.vehicle_id) ?? allocation?.original_vehicle_id ?? null;
  const targetVehicleId = text(capacityData.selected_vehicle_id) ?? allocation?.target_vehicle_id ?? null;
  const pickupPath = pathFromEvent(capacityData.pickup_route) ?? allocation?.pickup_route ?? null;
  const isBreakdown = anomalyType?.trim().toUpperCase() === "VEHICLE_BREAKDOWN" || text(capacityData.vehicle_status)?.toUpperCase() === "BROKEN";
  const vehicleReassigned = capacityData.vehicle_reassigned === true || allocation?.vehicle_reassigned === true;
  const movementNodeIds = isBreakdown && vehicleReassigned && targetVehicleId
    ? pickupPath?.node_ids ?? []
    : effectiveRoutePlan?.recommended_path?.node_ids ?? [];
  const movementPathKey = movementNodeIds.join("|");
  const movementNodeCount = movementNodeIds.length;
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const currentStep = movementNodeCount ? step % movementNodeCount : 0;

  useEffect(() => {
    if (!playing || movementNodeCount < 2) return undefined;
    const timer = window.setInterval(() => setStep((current) => (current + 1) % movementNodeCount), 1500);
    return () => window.clearInterval(timer);
  }, [movementPathKey, movementNodeCount, playing]);

  const failedNodeId = pickupPath?.node_ids.at(-1)
    ?? effectiveRoutePlan?.original_path?.node_ids.at(-1)
    ?? movementNodeIds[0]
    ?? null;
  const activeVehicleId = isBreakdown && vehicleReassigned ? targetVehicleId : originalVehicleId;
  const activeNodeId = movementNodeIds[currentStep] ?? null;
  const atPickupPoint = isBreakdown && movementNodeCount > 0 && currentStep === movementNodeCount - 1;
  const markers: RouteVehicleMarker[] = [];
  if (isBreakdown && originalVehicleId && failedNodeId) {
    markers.push({ vehicleId: originalVehicleId, nodeId: failedNodeId, state: "failed", label: `${originalVehicleId} · 故障车辆`, offsetX: -15 });
  }
  if (activeVehicleId && activeNodeId) {
    markers.push({ vehicleId: activeVehicleId, nodeId: activeNodeId, state: "moving", label: isBreakdown ? `${activeVehicleId} · 已派出` : `${activeVehicleId} · 绕行中`, offsetX: isBreakdown ? 15 : 0 });
  }

  return <section className="live-vehicle-map" aria-labelledby="live-vehicle-map-title">
    <div className="live-map-heading">
      <div><p className="eyebrow">管理员车辆态势</p><h2 id="live-vehicle-map-title">车辆实时调度地图</h2><p>员工上报、车辆接替和路线计算在同一张虚拟路网中联动。</p></div>
      <div className="live-map-badges"><span className="simulation-badge"><Radio size={13}/>虚拟沙盘实时模拟</span><span className={`connection-badge is-${connection.toLowerCase()}`}>{connectionCopy(connection)}</span></div>
    </div>
    <div className="live-vehicle-status" aria-live="polite">
      {isBreakdown && originalVehicleId ? <span className="is-failed"><Truck size={15}/><b>{originalVehicleId} · 故障车辆</b><small>{failedNodeId ? `停留 ${failedNodeId}` : "等待定位"}</small></span> : null}
      {activeVehicleId ? <span className="is-moving"><Truck size={15}/><b>{isBreakdown ? `${activeVehicleId} · 已派出` : `${activeVehicleId} · 执行新路线`}</b><small>{atPickupPoint ? "已到达接驳点" : activeNodeId ? `当前位置 ${activeNodeId}` : "等待路径"}</small></span> : <span><Truck size={15}/><b>等待 AI 选车</b><small>运力智能体计算中</small></span>}
      <span className="live-event-count"><Radio size={15}/><b>Agent 事件</b><small>已同步 {events.length} 个 Agent 实时事件</small></span>
      {movementNodeCount > 1 ? <button type="button" className="live-map-control" onClick={() => setPlaying((current) => !current)}>{playing ? <Pause size={14}/> : <Play size={14}/>} {playing ? "暂停模拟" : "继续模拟"}</button> : <button type="button" className="live-map-control" disabled><RotateCcw size={14}/>等待路线</button>}
    </div>
    {effectiveRoutePlan ? <RouteVisual routePlan={effectiveRoutePlan} pickupEdgeIds={pickupPath?.edge_ids ?? []} vehicleMarkers={markers}/> : <div className="live-map-waiting"><Truck size={24}/><strong>等待路径智能体生成虚拟路网</strong><span>故障状态已经接收，路线生成后车辆会自动出现在地图上。</span></div>}
    <div className="live-map-legend"><span data-kind="failed">故障车辆</span><span data-kind="moving">调度车辆</span><span data-kind="pickup">接驳路线</span><span data-kind="reroute">新规划路线</span><small>车辆位置每 1.5 秒更新 · 仅为虚拟节点模拟，不采集真实 GPS</small></div>
  </section>;
}
