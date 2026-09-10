import { Filter, LocateFixed, Pause, Play, Radio, Route, Truck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fleetEdges,
  fleetNodes,
  fleetRoadLabels,
  fleetRoutes,
  fleetStatusMeta,
  fleetVehicles,
  type FleetVehicleStatus,
} from "../features/fleet-sandbox/fleet-sandbox-data";
import { fleetRouteGeometry, fleetRoutePoints, fullFleetMapViewBox } from "../features/fleet-sandbox/fleet-map-geometry";
import { canonicalFleetVehicleId, fleetNodeById as nodeById, fleetPositionForVehicle, fleetRouteById as routeById, fleetSimulationTick, type FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";
import type { RoutePlanResponse, VehicleAllocationResponse } from "../services/api/dispatch-adapter";
import type { TaskEvent } from "../types/task-events";

interface FleetSandboxMapProps {
  anomalyType: string | null | undefined;
  allocation: VehicleAllocationResponse | null | undefined;
  routePlan: RoutePlanResponse | null | undefined;
  connection: "CONNECTED" | "RECONNECTING" | "DISCONNECTED";
  reportedVehicleId?: string | null;
  taskStatus?: string | null;
  events?: TaskEvent[];
}

function taskVehicleId(value: string | null | undefined): string | null {
  return canonicalFleetVehicleId(value);
}

function connectionLabel(connection: FleetSandboxMapProps["connection"]): string {
  if (connection === "CONNECTED") return "员工上报通道已连接";
  if (connection === "RECONNECTING") return "员工上报通道重连中";
  return "员工上报通道未连接";
}

export function FleetSandboxMap({ anomalyType, allocation, routePlan, connection, reportedVehicleId, taskStatus, events = [] }: FleetSandboxMapProps) {
  const normalizedAnomaly = anomalyType?.trim().toUpperCase();
  const originalVehicleId = taskVehicleId(allocation?.original_vehicle_id) ?? taskVehicleId(reportedVehicleId);
  const targetVehicleId = taskVehicleId(allocation?.target_vehicle_id);
  const [tick, setTick] = useState(() => fleetSimulationTick());
  const [playing, setPlaying] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"ALL" | FleetVehicleStatus>("ALL");
  const [selectedRouteId, setSelectedRouteId] = useState("ALL");
  const [selectedVehicleId, setSelectedVehicleId] = useState(() => originalVehicleId ?? "V-001");

  useEffect(() => {
    if (!playing) return undefined;
    const timer = window.setInterval(() => setTick(fleetSimulationTick()), 1500);
    return () => window.clearInterval(timer);
  }, [playing]);

  const runtimeVehicles = useMemo<FleetPositionSnapshot[]>(() => fleetVehicles.map((baseVehicle) => {
    let vehicle = baseVehicle;
    if (normalizedAnomaly === "VEHICLE_BREAKDOWN" && baseVehicle.id === originalVehicleId) {
      vehicle = { ...baseVehicle, status: "BROKEN", speedKph: 0 };
    }
    if (normalizedAnomaly === "VEHICLE_BREAKDOWN" && baseVehicle.id === targetVehicleId) {
      vehicle = { ...baseVehicle, routeId: "ROUTE-10", status: "DISPATCHING", speedKph: 46 };
    }
    if (normalizedAnomaly === "ROAD_BLOCKED" && baseVehicle.id === originalVehicleId) {
      vehicle = { ...baseVehicle, routeId: "ROUTE-02", status: "DISPATCHING", speedKph: 42 };
    }
    if (vehicle.status === "BROKEN" && normalizedAnomaly === "VEHICLE_BREAKDOWN" && vehicle.id === originalVehicleId) {
      vehicle = { ...vehicle, initialStep: 3 };
    }
    return fleetPositionForVehicle(vehicle, tick);
  }), [normalizedAnomaly, originalVehicleId, targetVehicleId, tick]);

  const selectedVehicle = runtimeVehicles.find((vehicle) => vehicle.id === selectedVehicleId) ?? runtimeVehicles[0];
  const selectedRoute = routeById.get(selectedVehicle.routeId) ?? fleetRoutes[0];
  const statusCounts = useMemo(() => runtimeVehicles.reduce<Record<FleetVehicleStatus, number>>((counts, vehicle) => {
    counts[vehicle.status] += 1;
    return counts;
  }, { IN_TRANSIT: 0, AVAILABLE: 0, DISPATCHING: 0, BROKEN: 0, MAINTENANCE: 0 }), [runtimeVehicles]);
  const visibleVehicles = runtimeVehicles.filter((vehicle) =>
    (statusFilter === "ALL" || vehicle.status === statusFilter)
    && (selectedRouteId === "ALL" || vehicle.routeId === selectedRouteId));
  const blockedEdgeIds = new Set(
    routePlan?.blocked_edge_ids?.length
      ? routePlan.blocked_edge_ids
      : normalizedAnomaly === "ROAD_BLOCKED"
        ? ["E04"]
        : [],
  );
  const routeFocus = selectedRouteId === "ALL" ? null : fleetRouteGeometry(selectedRouteId);
  const visibleRoutes = routeFocus ? [routeFocus.route] : fleetRoutes;
  const visibleNodes = routeFocus ? routeFocus.nodes : fleetNodes;
  const visibleEdges = routeFocus
    ? fleetEdges.filter((edge) => routeFocus.edgeIds.has(edge.id) || blockedEdgeIds.has(edge.id))
    : fleetEdges;
  const mapViewBox = routeFocus?.viewBox ?? fullFleetMapViewBox;

  const selectRoute = (routeId: string) => {
    setSelectedRouteId(routeId);
    if (routeId === "ALL") return;
    const firstVehicleOnRoute = runtimeVehicles.find((vehicle) => vehicle.routeId === routeId && (statusFilter === "ALL" || vehicle.status === statusFilter));
    if (firstVehicleOnRoute) setSelectedVehicleId(firstVehicleOnRoute.id);
  };

  const incidentSummary = normalizedAnomaly === "VEHICLE_BREAKDOWN" && originalVehicleId
    ? `异常已上报 · 故障车辆 ${originalVehicleId} 已锁定；${targetVehicleId ? `已派出替代车辆 ${targetVehicleId}` : "AI 正在选择替代车辆"}`
    : normalizedAnomaly === "ROAD_BLOCKED"
      ? `异常已上报 · 道路堵塞-02；${routePlan?.recommended_path ? `${originalVehicleId ?? "任务车辆"} 正在执行路线-02` : "AI 正在计算新路线"}`
      : "当前车队按固定虚拟路网运行，员工上报后将自动覆盖车辆状态。";

  return <section className="fleet-sandbox" aria-labelledby="fleet-sandbox-title">
    <header className="fleet-sandbox-heading">
      <div>
        <p className="eyebrow">管理员全车队沙盘</p>
        <h2 id="fleet-sandbox-title">20 辆车辆实时态势</h2>
        <p>10 条县域物流路线统一展示，车辆沿道路连续移动，完整路线约 3–5 分钟。</p>
      </div>
      <div className="fleet-sandbox-live-badges">
        <span className="simulation-badge"><Radio size={13}/>虚拟沙盘实时模拟，不采集真实 GPS · 1.5 秒刷新</span>
        <span className={`connection-badge is-${connection.toLowerCase()}`}>{connectionLabel(connection)}</span>
      </div>
    </header>

    <div className="fleet-incident-banner" role="status">
      <LocateFixed size={17}/><strong>{incidentSummary}</strong>
      {taskStatus ? <b className="fleet-task-stage">{taskStatus === "COMPLETED" ? "调度完成" : taskStatus === "PENDING" ? "等待AI处理" : "AI处理中"}</b> : null}
      <span>已同步 {events.length} 个实时事件</span>
      {normalizedAnomaly === "ROAD_BLOCKED" && routePlan?.recommended_path ? <small>新路线 {routePlan.recommended_path.distance_km} 公里 · 预计 {routePlan.recommended_path.estimated_minutes} 分钟</small> : null}
    </div>

    <div className="fleet-status-strip" aria-label="车队状态统计">
      {(Object.keys(fleetStatusMeta) as FleetVehicleStatus[]).map((status) => <button
        type="button"
        key={status}
        className={statusFilter === status ? "is-active" : ""}
        onClick={() => setStatusFilter((current) => current === status ? "ALL" : status)}
        style={{ "--fleet-status-color": fleetStatusMeta[status].color } as React.CSSProperties}
      ><i/><span>{fleetStatusMeta[status].label}</span><strong>{statusCounts[status]}</strong></button>)}
      <span className="fleet-total-count"><Truck size={15}/><b>共 20 辆</b></span>
    </div>

    <div className="fleet-sandbox-controls">
      <label><Filter size={14}/><span>车辆状态</span><select aria-label="筛选车辆状态" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "ALL" | FleetVehicleStatus)}><option value="ALL">全部状态</option>{(Object.keys(fleetStatusMeta) as FleetVehicleStatus[]).map((status) => <option key={status} value={status}>{fleetStatusMeta[status].label}（{statusCounts[status]}）</option>)}</select></label>
      <label><Route size={14}/><span>路线聚焦（隐藏其他路线）</span><select aria-label="选择高亮路线" value={selectedRouteId} onChange={(event) => selectRoute(event.target.value)}><option value="ALL">查看全部 10 条路线</option>{fleetRoutes.map((route) => <option data-route-id={route.id} key={route.id} value={route.id}>{route.displayId} · {route.name}</option>)}</select></label>
      <button type="button" className="fleet-play-control" onClick={() => setPlaying((current) => !current)}>{playing ? <Pause size={14}/> : <Play size={14}/>} {playing ? "暂停车辆移动" : "继续车辆移动"}</button>
    </div>

    <div className="fleet-sandbox-layout">
      <div className="fleet-sandbox-map-shell">
        <svg className="fleet-sandbox-canvas" data-map-focus={selectedRouteId} viewBox={mapViewBox} preserveAspectRatio="xMidYMid meet" role="img" aria-label="县域20辆车辆与10条路线实时沙盘">
          <defs>
            <pattern id="fleet-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="currentColor" strokeWidth="1"/></pattern>
          </defs>
          <rect className="fleet-map-grid" width="1200" height="680" fill="url(#fleet-grid)"/>
          <g className="fleet-map-terrain" aria-hidden="true"><path className="terrain-zone terrain-west" d="M42 70H360L430 260 300 500 45 575Z"/><path className="terrain-zone terrain-east" d="M835 60H1160V585L930 620 820 370Z"/><path className="fleet-river" d="M1040 20C900 150 980 250 810 330S650 520 520 665"/><text x="930" y="165">东河</text><text className="area-name" x="170" y="520">河西片区</text><text className="area-name" x="930" y="615">城东片区</text></g>
          <g className="fleet-base-roads">{visibleEdges.map((edge) => {
            const from = nodeById.get(edge.from); const to = nodeById.get(edge.to);
            return from && to ? <line
              key={edge.id}
              data-fleet-edge-id={edge.id}
              className={blockedEdgeIds.has(edge.id) ? "is-blocked" : ""}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
            /> : null;
          })}</g>
          <g className="fleet-route-lines">{visibleRoutes.map((route) => <polyline
            key={route.id}
            data-fleet-route-id={route.id}
            data-dispatch-state={
              normalizedAnomaly === "ROAD_BLOCKED" && route.id === "ROUTE-02"
                ? routePlan?.recommended_path ? "REROUTED" : "CALCULATING"
                : normalizedAnomaly === "VEHICLE_BREAKDOWN" && targetVehicleId && route.id === "ROUTE-10"
                  ? "RESCUE"
                  : undefined
            }
            points={fleetRoutePoints(route.id)}
            stroke={route.color}
            className={`${selectedRouteId === "ALL" || selectedRouteId === route.id ? "is-visible" : "is-muted"} ${
              normalizedAnomaly === "ROAD_BLOCKED" && route.id === "ROUTE-02"
                ? routePlan?.recommended_path ? "is-rerouted" : "is-calculating"
                : ""
            } ${
              normalizedAnomaly === "VEHICLE_BREAKDOWN" && targetVehicleId && route.id === "ROUTE-10"
                ? "is-rescue"
                : ""
            }`}
          />)}</g>
          <g className="fleet-road-names">{fleetRoadLabels.map((road) => <text key={road.id} data-road-name={road.id} x={road.x} y={road.y} transform={road.rotate ? `rotate(${road.rotate} ${road.x} ${road.y})` : undefined}>{road.name}</text>)}</g>
          <g className="fleet-route-labels">{visibleRoutes.map((route) => <g key={route.id} data-fleet-route-label={route.id} className="is-visible" transform={`translate(${route.labelX} ${route.labelY})`}><rect x="-104" y="-14" width="208" height="27" rx="7"/><circle cx="-90" cy="0" r="4" fill={route.color}/><text textAnchor="middle" x="8" y="4">{route.displayId} · {route.name}</text></g>)}</g>
          <g className="fleet-map-nodes">{visibleNodes.map((node) => <g key={node.id} data-fleet-stop-id={node.id} className={`is-${node.kind.toLowerCase()}`} transform={`translate(${node.x} ${node.y})`}>
            {node.kind === "HUB" ? <circle r="13"/> : node.kind === "STATION" ? <rect x="-9" y="-9" width="18" height="18" rx="4"/> : node.kind === "SERVICE" ? <path d="M0 -9 9 0 0 9 -9 0Z"/> : <circle r="6"/>}
            <text className="node-code" x="12" y="-5">{node.id}</text><text className="node-name" x="12" y="10">{node.name}</text>
          </g>)}</g>
          <g className="fleet-vehicle-markers">{visibleVehicles.map((vehicle, index) => {
            const color = fleetStatusMeta[vehicle.status].color;
            const labelY = index % 2 === 0 ? -13 : 17;
            return <g
              key={vehicle.id}
              role="button"
              tabIndex={0}
              aria-label={`${vehicle.id}，${fleetStatusMeta[vehicle.status].label}，${vehicle.locationLabel}`}
              data-fleet-vehicle-id={vehicle.id}
              data-fleet-status={vehicle.status}
              data-fleet-node-id={vehicle.nodeId}
              data-route-offset="0"
              className={`fleet-vehicle-marker ${selectedVehicle.id === vehicle.id ? "is-selected" : ""}`}
              transform={`translate(${vehicle.x.toFixed(2)} ${vehicle.y.toFixed(2)})`}
              onClick={() => setSelectedVehicleId(vehicle.id)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedVehicleId(vehicle.id); }}
            ><circle className="vehicle-halo" r="17" fill={color}/><circle className="vehicle-dot" r="9" fill={color}/><text x="13" y={labelY}>{vehicle.id}</text></g>;
          })}</g>
        </svg>
        <div className="fleet-map-legend">{(Object.keys(fleetStatusMeta) as FleetVehicleStatus[]).map((status) => <span key={status}><i style={{ background: fleetStatusMeta[status].color }}/>{fleetStatusMeta[status].label}</span>)}<span className="is-hub-stop"><i/>中心仓</span><span className="is-station-stop"><i/>配送/维修站</span><span className="is-service-stop"><i/>乡村服务点</span><small>地图范围：新平县虚拟路网 · 18 个命名站点 · 26 段道路</small></div>
      </div>

      <aside className="fleet-vehicle-panel" aria-label="车辆信息">
        <div className="fleet-selected-vehicle">
          <p>当前选中车辆</p><h3>{selectedVehicle.id}</h3>
          <span className={`fleet-status-pill is-${selectedVehicle.status.toLowerCase()}`}>{fleetStatusMeta[selectedVehicle.status].label}</span>
          <dl>
            <div><dt>执行路线</dt><dd>{selectedRoute.displayId} · {selectedRoute.name}</dd></div>
            <div><dt>当前位置</dt><dd>{selectedVehicle.locationLabel}</dd></div>
            <div><dt>实时速度</dt><dd>{selectedVehicle.speedKph} 公里/小时</dd></div>
            <div><dt>当前载重</dt><dd>{selectedVehicle.loadKg} / {selectedVehicle.capacityKg} 千克</dd></div>
            <div><dt>路线进度</dt><dd>{selectedVehicle.progress}%</dd></div>
          </dl>
          <div className="fleet-progress"><i style={{ width: `${selectedVehicle.progress}%` }}/></div>
        </div>
        <div className="fleet-roster-heading"><strong>车辆清单</strong><span>{visibleVehicles.length} / 20</span></div>
        <div className="fleet-roster">{visibleVehicles.map((vehicle) => {
          const route = routeById.get(vehicle.routeId) ?? fleetRoutes[0];
          const node = nodeById.get(vehicle.nodeId) ?? fleetNodes[0];
          return <button type="button" key={vehicle.id} data-fleet-roster-id={vehicle.id} className={selectedVehicle.id === vehicle.id ? "is-selected" : ""} onClick={() => setSelectedVehicleId(vehicle.id)}>
            <i style={{ background: fleetStatusMeta[vehicle.status].color }}/><span><b>{vehicle.id}</b><small>{route.displayId} · {node.name}</small></span><em>{fleetStatusMeta[vehicle.status].label}</em>
          </button>;
        })}</div>
      </aside>
    </div>
  </section>;
}
