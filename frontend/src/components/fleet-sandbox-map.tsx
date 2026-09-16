import { AlertTriangle, Crosshair, Filter, History, Layers3, LocateFixed, MapPinned, Maximize2, Minimize2, Minus, MoonStar, Navigation, Pause, Play, Plus, Radio, Route, Satellite, TrendingUp, Truck, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import {
  fleetEdges,
  fleetNodes,
  fleetRoadLabels,
  fleetRoutes,
  fleetStatusMeta,
  fleetVehicles,
  type FleetVehicleStatus,
} from "../features/fleet-sandbox/fleet-sandbox-data";
import { fleetEdgePath, fleetRouteGeometry, fleetRoutePath, fullFleetMapViewBox } from "../features/fleet-sandbox/fleet-map-geometry";
import { fleetOperationRouteSpecs, fleetVehicleTripDetails } from "../features/fleet-sandbox/fleet-operation-presentation";
import { canonicalFleetVehicleId, fleetNodeById as nodeById, fleetPositionForVehicle, fleetRouteById as routeById, fleetSimulationTick, type FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";
import type { DispatchImpactResponse, RoutePlanResponse, VehicleAllocationResponse } from "../services/api/dispatch-adapter";
import type { TaskEvent } from "../types/task-events";
import type { VehicleOperationSnapshot } from "../types/vehicle-operations";
import { AmapFleetMap, type AmapLoadState } from "./amap-fleet-map";
import { FleetVehicleDetailCard } from "./fleet-vehicle-detail-card";
import { MapErrorBoundary } from "./map-error-boundary";
import { VehicleOperationTimeline } from "./vehicle-operation-timeline";

interface FleetSandboxMapProps {
  anomalyType: string | null | undefined;
  allocation: VehicleAllocationResponse | null | undefined;
  routePlan: RoutePlanResponse | null | undefined;
  dispatchImpact?: DispatchImpactResponse | null;
  connection: "CONNECTED" | "RECONNECTING" | "DISCONNECTED";
  reportedVehicleId?: string | null;
  taskStatus?: string | null;
  events?: TaskEvent[];
  operationSnapshot?: VehicleOperationSnapshot | null;
  autoRevealVehicleId?: string | null;
}

function taskVehicleId(value: string | null | undefined): string | null {
  return canonicalFleetVehicleId(value);
}

function connectionLabel(connection: FleetSandboxMapProps["connection"]): string {
  if (connection === "CONNECTED") return "员工上报通道已连接";
  if (connection === "RECONNECTING") return "员工上报通道重连中";
  return "员工上报通道未连接";
}

function zoomViewBox(value: string, zoom: number, offset: { x: number; y: number }): string {
  const [x, y, width, height] = value.split(" ").map(Number);
  if ([x, y, width, height].some((item) => !Number.isFinite(item))) return value;
  const nextWidth = width / zoom;
  const nextHeight = height / zoom;
  return `${x + (width - nextWidth) / 2 + offset.x} ${y + (height - nextHeight) / 2 + offset.y} ${nextWidth} ${nextHeight}`;
}


export function FleetSandboxMap({ anomalyType, allocation, routePlan, dispatchImpact = null, connection, reportedVehicleId, taskStatus, events = [], operationSnapshot = null, autoRevealVehicleId = null }: FleetSandboxMapProps) {
  const normalizedAnomaly = anomalyType?.trim().toUpperCase();
  const originalVehicleId = taskVehicleId(allocation?.original_vehicle_id) ?? taskVehicleId(reportedVehicleId);
  const targetVehicleId = taskVehicleId(allocation?.target_vehicle_id);
  const initiallyRevealedVehicleId = taskVehicleId(autoRevealVehicleId);
  const [tick, setTick] = useState(() => fleetSimulationTick());
  const [playing, setPlaying] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"ALL" | FleetVehicleStatus>("ALL");
  const [selectedRouteId, setSelectedRouteId] = useState("ALL");
  const [selectedVehicleId, setSelectedVehicleId] = useState(() => initiallyRevealedVehicleId ?? originalVehicleId ?? "V-001");
  const [detailVehicleId, setDetailVehicleId] = useState<string | null>(() => initiallyRevealedVehicleId);
  const [mapMode, setMapMode] = useState<"STANDARD" | "SATELLITE">("STANDARD");
  const [zoom, setZoom] = useState(1);
  const [showLabels, setShowLabels] = useState(true);
  const [showRoutes, setShowRoutes] = useState(true);
  const [showNodes, setShowNodes] = useState(true);
  const [showRiskAreas, setShowRiskAreas] = useState(true);
  const [perspective, setPerspective] = useState(false);
  const [businessMode, setBusinessMode] = useState<"LIVE" | "HISTORY" | "GEOFENCE">("LIVE");
  const [showTraffic, setShowTraffic] = useState(false);
  const [mapResetSequence, setMapResetSequence] = useState(0);
  const [layerPanelOpen, setLayerPanelOpen] = useState(false);
  const [viewportOffset, setViewportOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [followVehicle, setFollowVehicle] = useState(() => Boolean(initiallyRevealedVehicleId));
  const [amapState, setAmapState] = useState<AmapLoadState>(runtimeConfig.amap?.enabled ? "LOADING" : "FALLBACK");
  const dragOrigin = useRef<{ clientX: number; clientY: number; offsetX: number; offsetY: number } | null>(null);

  useEffect(() => {
    if (!playing) return undefined;
    const timer = window.setInterval(() => setTick(fleetSimulationTick()), 250);
    return () => window.clearInterval(timer);
  }, [playing]);

  useEffect(() => {
    if (!fullscreen) return undefined;
    const exitFullscreen = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", exitFullscreen);
    return () => window.removeEventListener("keydown", exitFullscreen);
  }, [fullscreen]);

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
    const operationVehicle = operationSnapshot?.vehicles.find((candidate) => candidate.vehicle_id === baseVehicle.id);
    if (operationVehicle) {
      const status = operationVehicle.status === "AVAILABLE"
        ? "AVAILABLE"
        : operationVehicle.status === "IN_TRANSIT"
          ? "IN_TRANSIT"
          : operationVehicle.status === "DISPATCHING"
            ? "DISPATCHING"
            : operationVehicle.status === "MAINTENANCE" || operationVehicle.status === "QA_PENDING"
              ? "MAINTENANCE"
              : "BROKEN";
      vehicle = {
        ...vehicle,
        status,
        loadKg: Number(operationVehicle.current_load_kg ?? vehicle.loadKg),
        capacityKg: Number(operationVehicle.max_load_kg ?? vehicle.capacityKg),
        speedKph: status === "IN_TRANSIT" || status === "DISPATCHING" ? Math.max(vehicle.speedKph, 38) : 0,
      };
    }
    const position = fleetPositionForVehicle(vehicle, tick);
    if (!operationVehicle || position.status === "IN_TRANSIT" || position.status === "DISPATCHING") return position;
    const node = nodeById.get(operationVehicle.current_node_id);
    return node ? { ...position, nodeId: node.id, x: node.x, y: node.y, locationLabel: node.name } : position;
  }), [normalizedAnomaly, operationSnapshot, originalVehicleId, targetVehicleId, tick]);

  const selectedVehicle = runtimeVehicles.find((vehicle) => vehicle.id === selectedVehicleId) ?? runtimeVehicles[0];
  const selectedRoute = routeById.get(selectedVehicle.routeId) ?? fleetRoutes[0];
  const selectedTrip = fleetVehicleTripDetails(selectedVehicle, selectedRoute);
  const selectedOperationVehicle = operationSnapshot?.vehicles.find((vehicle) => vehicle.vehicle_id === selectedVehicle.id);
  const operationRoutes = useMemo(() => fleetOperationRouteSpecs(operationSnapshot), [operationSnapshot]);
  const statusCounts = useMemo(() => runtimeVehicles.reduce<Record<FleetVehicleStatus, number>>((counts, vehicle) => {
    counts[vehicle.status] += 1;
    return counts;
  }, { IN_TRANSIT: 0, AVAILABLE: 0, DISPATCHING: 0, BROKEN: 0, MAINTENANCE: 0 }), [runtimeVehicles]);
  const visibleVehicles = runtimeVehicles.filter((vehicle) =>
    (statusFilter === "ALL" || vehicle.status === statusFilter)
    && (selectedRouteId === "ALL" || vehicle.routeId === selectedRouteId));
  const mileageRanking = runtimeVehicles.slice().sort((left, right) => right.progress - left.progress).slice(0, 5);
  const activeVehicleCount = statusCounts.IN_TRANSIT + statusCounts.DISPATCHING;
  const blockedEdgeIds = new Set(
    routePlan?.blocked_edge_ids?.length
      ? routePlan.blocked_edge_ids
      : normalizedAnomaly === "ROAD_BLOCKED"
        ? ["E04"]
        : [],
  );
  const onlineVehicleCount = activeVehicleCount + statusCounts.AVAILABLE;
  const abnormalVehicleCount = statusCounts.BROKEN + statusCounts.MAINTENANCE;
  const alertCount = abnormalVehicleCount + blockedEdgeIds.size + (connection === "RECONNECTING" ? 1 : 0);
  const todayMileage = runtimeVehicles.reduce((total, vehicle) => total + Math.round(92 + vehicle.progress * .72), 0);
  const routeFocus = selectedRouteId === "ALL" ? null : fleetRouteGeometry(selectedRouteId);
  const visibleRoutes = routeFocus ? [routeFocus.route] : fleetRoutes;
  const visibleNodes = routeFocus ? routeFocus.nodes : fleetNodes;
  const visibleEdges = routeFocus
    ? fleetEdges.filter((edge) => routeFocus.edgeIds.has(edge.id) || blockedEdgeIds.has(edge.id))
    : fleetEdges;
  const mapViewBox = zoomViewBox(routeFocus?.viewBox ?? fullFleetMapViewBox, zoom, viewportOffset);
  const criticalRouteIds = Array.from(new Set([
    selectedRouteId !== "ALL" ? selectedRouteId : selectedVehicle.routeId,
    normalizedAnomaly === "ROAD_BLOCKED" ? "ROUTE-02" : null,
    normalizedAnomaly === "VEHICLE_BREAKDOWN" && targetVehicleId ? "ROUTE-10" : null,
  ].filter((routeId): routeId is string => Boolean(routeId))));
  const shouldRenderLegacyMap = !runtimeConfig.amap?.enabled || amapState === "FALLBACK";
  const impactIncidentVehicleId = taskVehicleId(dispatchImpact?.incident_vehicle_id);
  const impactReplacementVehicleId = taskVehicleId(dispatchImpact?.replacement_vehicle_id);
  const detailVehicle = detailVehicleId
    ? runtimeVehicles.find((vehicle) => vehicle.id === detailVehicleId) ?? null
    : null;
  const detailRoute = detailVehicle ? routeById.get(detailVehicle.routeId) ?? fleetRoutes[0] : null;
  const detailTrip = detailVehicle && detailRoute ? fleetVehicleTripDetails(detailVehicle, detailRoute) : null;
  const detailOperationVehicle = detailVehicle
    ? operationSnapshot?.vehicles.find((vehicle) => vehicle.vehicle_id === detailVehicle.id)
    : null;
  const visibleDispatchImpact = dispatchImpact && (
    detailVehicleId === impactIncidentVehicleId
    || detailVehicleId === impactReplacementVehicleId
  ) ? dispatchImpact : null;

  const selectVehicle = (vehicleId: string) => {
    setSelectedVehicleId(vehicleId);
    setDetailVehicleId(vehicleId);
  };

  const resetMapView = () => {
    setFollowVehicle(false);
    setDetailVehicleId(null);
    setSelectedRouteId("ALL");
    setZoom(1);
    setViewportOffset({ x: 0, y: 0 });
    setMapResetSequence((value) => value + 1);
  };

  const selectRoute = (routeId: string) => {
    setDetailVehicleId(null);
    setSelectedRouteId(routeId);
    setZoom(1);
    if (routeId === "ALL") return;
    const firstVehicleOnRoute = runtimeVehicles.find((vehicle) => vehicle.routeId === routeId && (statusFilter === "ALL" || vehicle.status === statusFilter));
    if (firstVehicleOnRoute) setSelectedVehicleId(firstVehicleOnRoute.id);
    setViewportOffset({ x: 0, y: 0 });
  };

  const startMapDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    if ((event.target as Element).closest('[role="button"]')) return;
    setFollowVehicle(false);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragOrigin.current = { clientX: event.clientX, clientY: event.clientY, offsetX: viewportOffset.x, offsetY: viewportOffset.y };
    setDragging(true);
  };

  const moveMap = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!dragOrigin.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const [, , viewWidth, viewHeight] = mapViewBox.split(" ").map(Number);
    const deltaX = (event.clientX - dragOrigin.current.clientX) * viewWidth / Math.max(bounds.width, 1);
    const deltaY = (event.clientY - dragOrigin.current.clientY) * viewHeight / Math.max(bounds.height, 1);
    setViewportOffset({ x: dragOrigin.current.offsetX - deltaX, y: dragOrigin.current.offsetY - deltaY });
  };

  const finishMapDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    dragOrigin.current = null;
    setDragging(false);
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
        <p>杨林物流走廊 10 条业务路线统一展示，车辆沿高德规划道路连续移动。</p>
      </div>
      <div className="fleet-sandbox-live-badges">
        <span className="simulation-badge"><Radio size={13}/>虚拟沙盘实时模拟，不采集真实 GPS · 连续轨迹动画</span>
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

    <div className="fleet-command-kpis" aria-label="车辆实时核心指标">
      <article data-fleet-kpi="online" className="is-cyan">
        <span className="fleet-command-kpi__icon"><Truck size={23}/></span>
        <span><small>在线车辆</small><strong>{onlineVehicleCount}<em> / {runtimeVehicles.length}</em></strong><b>在线率 {Math.round(onlineVehicleCount / runtimeVehicles.length * 100)}%</b></span>
        <i className="fleet-command-kpi__spark" aria-hidden="true">{[2, 4, 3, 6, 5, 8].map((height, index) => <u key={index} style={{ height: `${height * 7}%` }}/>)}</i>
      </article>
      <article data-fleet-kpi="transit" className="is-blue">
        <span className="fleet-command-kpi__icon"><Navigation size={23}/></span>
        <span><small>运输中</small><strong>{activeVehicleCount}</strong><b>路线连续运行</b></span>
        <i className="fleet-command-kpi__spark" aria-hidden="true">{[3, 4, 5, 4, 7, 8].map((height, index) => <u key={index} style={{ height: `${height * 7}%` }}/>)}</i>
      </article>
      <article data-fleet-kpi="abnormal" className="is-red">
        <span className="fleet-command-kpi__icon"><AlertTriangle size={23}/></span>
        <span><small>异常车辆</small><strong>{abnormalVehicleCount}</strong><b>{abnormalVehicleCount ? "处置流程已启动" : "当前运行正常"}</b></span>
        <i className="fleet-command-kpi__spark" aria-hidden="true">{[2, 3, 2, 5, 4, 6].map((height, index) => <u key={index} style={{ height: `${height * 7}%` }}/>)}</i>
      </article>
      <article data-fleet-kpi="alerts" className="is-amber">
        <span className="fleet-command-kpi__icon"><Radio size={23}/></span>
        <span><small>今日告警</small><strong>{alertCount}</strong><b>{blockedEdgeIds.size ? `${blockedEdgeIds.size} 个道路风险点` : "风险通道实时监测"}</b></span>
        <i className="fleet-command-kpi__spark" aria-hidden="true">{[5, 3, 6, 4, 7, 5].map((height, index) => <u key={index} style={{ height: `${height * 7}%` }}/>)}</i>
      </article>
    </div>

    <div className="fleet-sandbox-layout">
      <div className={`fleet-sandbox-map-shell ${mapMode === "SATELLITE" ? "is-satellite" : "is-standard"} ${perspective ? "is-perspective" : ""} ${fullscreen ? "is-fullscreen" : ""}`}>
        <div className="fleet-map-command-tabs" aria-label="地图业务模式">
          <button type="button" className={businessMode === "LIVE" ? "is-active" : ""} onClick={() => { setBusinessMode("LIVE"); setPlaying(true); }}><Radio size={15}/>实时监控</button>
          <button type="button" className={businessMode === "HISTORY" ? "is-active" : ""} onClick={() => { setBusinessMode("HISTORY"); setPlaying(false); setShowRoutes(true); }}><History size={15}/>历史轨迹</button>
          <button type="button" className={businessMode === "GEOFENCE" ? "is-active" : ""} onClick={() => { setBusinessMode("GEOFENCE"); setShowRiskAreas(true); }}><MapPinned size={15}/>电子围栏</button>
          <button type="button" className={showTraffic ? "is-active" : ""} onClick={() => setShowTraffic((value) => !value)}><Route size={15}/>路况图层</button>
        </div>
        <button type="button" className="fleet-layer-panel-toggle" aria-label={layerPanelOpen ? "收起地图图层" : "展开地图图层"} aria-expanded={layerPanelOpen} title={layerPanelOpen ? "收起图层" : "展开图层"} onClick={() => setLayerPanelOpen((value) => !value)}><Layers3 size={17}/></button>
        <aside className={`fleet-map-layer-panel ${layerPanelOpen ? "is-open" : ""}`} aria-label="地图图层与车辆状态">
          <h3><Truck size={16}/>车辆状态</h3>
          <button type="button" className={statusFilter === "ALL" ? "is-active" : ""} onClick={() => setStatusFilter("ALL")}><i className="is-all"/><span>全部车辆</span><b>20</b></button>
          {(Object.keys(fleetStatusMeta) as FleetVehicleStatus[]).map((status) => <button type="button" key={status} className={statusFilter === status ? "is-active" : ""} onClick={() => setStatusFilter(status)}><i style={{ background: fleetStatusMeta[status].color }}/><span>{fleetStatusMeta[status].label}</span><b>{statusCounts[status]}</b></button>)}
          <div className="fleet-map-layer-divider"/>
          <label><input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)}/><span>显示车辆编号</span></label>
          <label><input type="checkbox" checked={showRoutes} onChange={(event) => setShowRoutes(event.target.checked)}/><span>显示行驶轨迹</span></label>
          <label><input type="checkbox" checked={showNodes} onChange={(event) => setShowNodes(event.target.checked)}/><span>显示配送网点</span></label>
          <label><input type="checkbox" checked={showRiskAreas} onChange={(event) => setShowRiskAreas(event.target.checked)}/><span>显示风险区域</span></label>
          <select aria-label="地图路线聚焦" value={selectedRouteId} onChange={(event) => selectRoute(event.target.value)}><option value="ALL">全部 10 条路线</option>{fleetRoutes.map((route) => <option key={route.id} value={route.id}>{route.displayId}</option>)}</select>
        </aside>
        <div className="fleet-map-mode-control" aria-label="地图模式">
          <button type="button" className={perspective ? "is-active" : ""} aria-label="切换三维地图" onClick={() => setPerspective((value) => !value)}>3D</button>
          <button type="button" className={mapMode === "SATELLITE" ? "is-active" : ""} aria-label="切换卫星地图" onClick={() => setMapMode("SATELLITE")}><Satellite size={14}/>卫星</button>
          <button type="button" className={mapMode === "STANDARD" ? "is-active" : ""} aria-label="切换夜间地图" onClick={() => setMapMode("STANDARD")}><MoonStar size={14}/>夜景</button>
          <button type="button" className={showTraffic ? "is-active" : ""} aria-label="切换交通路况" onClick={() => setShowTraffic((value) => !value)}><Navigation size={14}/>交通</button>
        </div>
        <div className="fleet-map-floating-tools" aria-label="地图工具">
          <button type="button" aria-label="放大全景地图" title="放大" disabled={zoom >= 2} onClick={() => setZoom((value) => Math.min(2, Number((value + 0.25).toFixed(2))))}><Plus size={17}/></button>
          <button type="button" aria-label="缩小全景地图" title="缩小" disabled={zoom <= 1} onClick={() => setZoom((value) => Math.max(1, Number((value - 0.25).toFixed(2))))}><Minus size={17}/></button>
          <button type="button" aria-label="切换地图标注" title="地图标注" className={showLabels ? "is-active" : ""} onClick={() => setShowLabels((value) => !value)}><Layers3 size={17}/></button>
          <button type="button" aria-label="复位全景地图" title="复位" onClick={resetMapView}><LocateFixed size={17}/></button>
          <button type="button" aria-label={followVehicle ? "停止跟随车辆" : "跟随选中车辆"} title={followVehicle ? "停止跟车" : "跟随选中车辆"} aria-pressed={followVehicle} className={followVehicle ? "is-active" : ""} onClick={() => setFollowVehicle((value) => !value)}><Crosshair size={17}/></button>
          <button type="button" aria-label={fullscreen ? "退出全屏地图" : "全屏查看地图"} title={fullscreen ? "退出全屏" : "全屏"} aria-pressed={fullscreen} onClick={() => setFullscreen((value) => !value)}>{fullscreen ? <Minimize2 size={17}/> : <Maximize2 size={17}/>}</button>
        </div>
        <span className="fleet-map-coordinate">嵩明县杨林物流走廊 · {Math.round(zoom * 100)}%</span>
        <span className={`fleet-map-provider is-${amapState.toLowerCase()}`}><i/>{amapState === "READY" ? "高德实时路网" : amapState === "LOADING" ? "正在连接高德地图" : "本地地图保障模式"}</span>
        <span className="fleet-map-attribution">{amapState === "READY" ? "地图服务 © 高德地图 · CountyFlow 调度覆盖物" : "遥感影像 © Esri · 业务路网为演示叠加"}</span>
        {detailVehicle && detailRoute && detailTrip ? <FleetVehicleDetailCard
          vehicle={detailVehicle}
          route={detailRoute}
          trip={detailTrip}
          statusLabel={fleetStatusMeta[detailVehicle.status].label}
          statusColor={fleetStatusMeta[detailVehicle.status].color}
          driverId={detailOperationVehicle?.assigned_driver_id}
          statusReason={detailOperationVehicle?.status_reason}
          impact={visibleDispatchImpact}
          onClose={() => setDetailVehicleId(null)}
        /> : null}
        {runtimeConfig.amap?.enabled ? <MapErrorBoundary onFallback={() => setAmapState("FALLBACK")}><AmapFleetMap
          apiKey={runtimeConfig.amap.key}
          securityCode={runtimeConfig.amap.securityCode}
          vehicles={visibleVehicles}
          playing={playing}
          routeIds={visibleRoutes.map((route) => route.id)}
          nodeIds={visibleNodes.map((node) => node.id)}
          criticalRouteIds={criticalRouteIds}
          selectedVehicleId={selectedVehicle.id}
          blockedEdgeIds={[...blockedEdgeIds]}
          mapMode={mapMode}
          perspective={perspective}
          zoom={zoom}
          resetSequence={mapResetSequence}
          followVehicle={followVehicle}
          showLabels={showLabels}
          showRoutes={showRoutes}
          showNodes={showNodes}
          showRiskAreas={showRiskAreas}
          showTraffic={showTraffic}
          geofenceMode={businessMode === "GEOFENCE"}
          onFollowChange={setFollowVehicle}
          operationSnapshot={operationSnapshot}
          onVehicleSelect={selectVehicle}
          onRouteSelect={selectRoute}
          onStateChange={setAmapState}
        /></MapErrorBoundary> : null}
        {shouldRenderLegacyMap ? <svg className={`fleet-sandbox-canvas ${showLabels ? "" : "labels-hidden"} ${showRoutes ? "" : "routes-hidden"} ${showNodes ? "" : "nodes-hidden"} ${showRiskAreas ? "" : "risks-hidden"} ${dragging ? "is-panning" : ""}`} data-interactive="true" data-map-mode={mapMode} data-map-focus={selectedRouteId} viewBox={mapViewBox} preserveAspectRatio="xMidYMid meet" role="img" aria-label="县域20辆车辆与10条路线实时沙盘，可拖拽平移并使用滚轮缩放"
          onPointerDown={startMapDrag}
          onPointerMove={moveMap}
          onPointerUp={finishMapDrag}
          onPointerCancel={finishMapDrag}
          onWheel={(event) => {
            event.preventDefault();
            setZoom((value) => Math.max(1, Math.min(2, Number((value + (event.deltaY < 0 ? .25 : -.25)).toFixed(2)))));
          }}
        >
          <defs>
            <linearGradient id="fleet-satellite-base" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#344a32"/><stop offset=".42" stopColor="#607249"/><stop offset=".72" stopColor="#53694f"/><stop offset="1" stopColor="#293f42"/></linearGradient>
            <linearGradient id="fleet-sea" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#2f6577"/><stop offset="1" stopColor="#153f5a"/></linearGradient>
            <linearGradient id="fleet-urban" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#909181"/><stop offset="1" stopColor="#5f6b61"/></linearGradient>
            <filter id="fleet-terrain-texture" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".018 .05" numOctaves="4" seed="19" result="noise"/><feColorMatrix in="noise" type="saturate" values=".45" result="mutedNoise"/><feBlend in="SourceGraphic" in2="mutedNoise" mode="multiply"/></filter>
            <filter id="fleet-terrain-shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="8" stdDeviation="8" floodColor="#081b18" floodOpacity=".72"/></filter>
            <pattern id="fleet-fields" width="52" height="34" patternUnits="userSpaceOnUse" patternTransform="rotate(-13)"><rect width="52" height="34" fill="#718057"/><path d="M0 8H52M0 18H52M0 28H52" stroke="#9a9a62" strokeWidth="2" opacity=".44"/><path d="M13 0V34M39 0V34" stroke="#455c3f" strokeWidth="1" opacity=".42"/></pattern>
            <pattern id="fleet-city-grid" width="22" height="18" patternUnits="userSpaceOnUse" patternTransform="rotate(12)"><rect width="22" height="18" fill="#697269"/><path d="M0 4H22M5 0V18M16 0V18" stroke="#a6a99b" strokeWidth="2" opacity=".48"/></pattern>
            <clipPath id="fleet-county-clip"><path d="M64 383L82 282 130 197 210 128 302 92 398 60 495 69 585 40 688 57 780 42 879 75 973 84 1069 137 1127 219 1144 316 1120 414 1070 506 988 563 897 599 806 623 710 612 615 641 518 626 424 650 330 621 252 584 168 557 104 492Z"/></clipPath>
            <marker id="fleet-operation-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0 0L7 3L0 6Z"/></marker>
          </defs>
          <g className="fleet-map-terrain-satellite" aria-hidden="true">
            <image className="fleet-map-aerial-image" href="/assets/maps/xinping-satellite.webp" x="0" y="0" width="1200" height="680" preserveAspectRatio="xMidYMid slice"/>
            <rect className="fleet-map-sea" width="1200" height="680" fill="url(#fleet-sea)"/>
            <g clipPath="url(#fleet-county-clip)">
              <rect width="1200" height="680" fill="url(#fleet-satellite-base)"/>
              <rect className="fleet-terrain-noise" width="1200" height="680" fill="#748064" filter="url(#fleet-terrain-texture)" opacity=".82"/>
              <path className="fleet-mountain-range is-west" d="M-20 330C70 195 136 88 262 42C203 155 241 246 352 330C253 298 146 373 82 508Z"/>
              <path className="fleet-mountain-range is-north" d="M246 92C420 15 646 7 836 52C739 91 710 159 727 238C608 178 478 185 348 252Z"/>
              <path className="fleet-mountain-range is-east" d="M906 44C1060 57 1188 141 1235 257L1150 493C1078 390 1042 286 915 219Z"/>
              <path className="fleet-farmland" d="M256 286C372 217 548 208 683 260C746 284 766 365 705 408C570 483 362 451 262 378Z" fill="url(#fleet-fields)"/>
              <path className="fleet-farmland is-south" d="M376 454C539 404 779 430 921 521C839 612 584 664 385 596Z" fill="url(#fleet-fields)"/>
              <path className="fleet-urban-zone" d="M690 209C794 171 934 188 1012 263C984 351 893 409 779 385C702 369 653 285 690 209Z" fill="url(#fleet-city-grid)"/>
              <path className="fleet-river-main" d="M1030 -18C955 88 1004 164 902 230C824 281 850 341 746 394C633 452 655 536 527 704"/>
              <path className="fleet-river-branch" d="M899 229C814 207 739 172 661 111"/>
              <g className="fleet-terrain-ridges"><path d="M74 294C144 183 205 130 294 92"/><path d="M89 352C171 244 239 204 327 175"/><path d="M126 445C218 340 281 316 367 303"/><path d="M341 126C461 78 548 72 660 91"/><path d="M845 101C945 123 1031 171 1091 244"/><path d="M905 478C1007 445 1079 394 1131 322"/></g>
            </g>
            <path className="fleet-county-boundary" d="M64 383L82 282 130 197 210 128 302 92 398 60 495 69 585 40 688 57 780 42 879 75 973 84 1069 137 1127 219 1144 316 1120 414 1070 506 988 563 897 599 806 623 710 612 615 641 518 626 424 650 330 621 252 584 168 557 104 492Z" filter="url(#fleet-terrain-shadow)"/>
            <g className="fleet-risk-zones"><circle cx="680" cy="235" r="54"/><circle cx="915" cy="416" r="42"/></g>
            <text className="fleet-county-name" x="575" y="350">嵩明县</text>
            <text className="fleet-region-label" x="152" y="555">杨林西片区</text><text className="fleet-region-label" x="930" y="545">空港东片区</text>
          </g>
          <g className="fleet-road-casings" aria-hidden="true">{visibleEdges.map((edge) => <path key={`casing-${edge.id}`} d={fleetEdgePath(edge)}/>)}</g>
          <g className="fleet-base-roads">{visibleEdges.map((edge) => <path key={edge.id} data-fleet-edge-id={edge.id} className={blockedEdgeIds.has(edge.id) ? "is-blocked" : ""} d={fleetEdgePath(edge)}/>)}</g>
          <g className="fleet-route-lines">{visibleRoutes.map((route) => <path
            role="button"
            tabIndex={0}
            aria-label={`聚焦${route.displayId}：${route.name}`}
            key={route.id}
            data-fleet-route-id={route.id}
            data-map-priority={
              selectedRouteId === route.id
              || selectedVehicle.routeId === route.id
              || (normalizedAnomaly === "ROAD_BLOCKED" && route.id === "ROUTE-02")
              || (normalizedAnomaly === "VEHICLE_BREAKDOWN" && targetVehicleId && route.id === "ROUTE-10")
                ? "critical"
                : "background"
            }
            data-dispatch-state={
              normalizedAnomaly === "ROAD_BLOCKED" && route.id === "ROUTE-02"
                ? routePlan?.recommended_path ? "REROUTED" : "CALCULATING"
                : normalizedAnomaly === "VEHICLE_BREAKDOWN" && targetVehicleId && route.id === "ROUTE-10"
                  ? "RESCUE"
                  : undefined
            }
            d={fleetRoutePath(route.id)}
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
            onClick={() => selectRoute(route.id)}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") selectRoute(route.id); }}
          />)}</g>
          <g className="fleet-operation-routes">{operationRoutes.map((route) => <g key={route.id} data-operation-map-route={route.kind} className={`is-${route.kind.toLowerCase()}`}>
            {route.nodeIds.slice(0, -1).map((nodeId, index) => {
              const from = nodeById.get(nodeId);
              const to = nodeById.get(route.nodeIds[index + 1]);
              return from && to ? <line key={`${route.id}-${nodeId}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} markerEnd="url(#fleet-operation-arrow)"/> : null;
            })}
          </g>)}</g>
          <g className="fleet-road-names">{fleetRoadLabels.map((road) => <text key={road.id} data-road-name={road.id} x={road.x} y={road.y} transform={road.rotate ? `rotate(${road.rotate} ${road.x} ${road.y})` : undefined}>{road.name}</text>)}</g>
          <g className="fleet-road-shields" aria-label="主要道路编号">
            {[
              { id: "G56", x: 520, y: 441, level: "expressway" },
              { id: "G85", x: 823, y: 476, level: "national" },
              { id: "S101", x: 474, y: 202, level: "provincial" },
              { id: "X012", x: 270, y: 173, level: "county" },
            ].map((road) => <g key={road.id} data-road-shield={road.id} className={`is-${road.level}`} transform={`translate(${road.x} ${road.y})`}>
              <rect x="-23" y="-11" width="46" height="22" rx="3"/>
              <text textAnchor="middle" y="4">{road.id}</text>
            </g>)}
          </g>
          <g className="fleet-route-labels">{visibleRoutes.map((route) => <g key={route.id} data-fleet-route-label={route.id} className="is-visible" transform={`translate(${route.labelX} ${route.labelY})`}><rect x="-104" y="-14" width="208" height="27" rx="7"/><circle cx="-90" cy="0" r="4" fill={route.color}/><text textAnchor="middle" x="8" y="4">{route.displayId} · {route.name}</text></g>)}</g>
          <g className="fleet-map-nodes">{visibleNodes.map((node) => <g key={node.id} data-fleet-stop-id={node.id} className={`is-${node.kind.toLowerCase()}`} transform={`translate(${node.x} ${node.y})`}>
            {node.kind === "HUB" ? <circle r="13"/> : node.kind === "STATION" ? <rect x="-9" y="-9" width="18" height="18" rx="4"/> : node.kind === "SERVICE" ? <path d="M0 -9 9 0 0 9 -9 0Z"/> : <circle r="6"/>}
            <text className="node-code" x="12" y="-5">{node.id}</text><text className="node-name" x="12" y="10">{node.name}</text>
          </g>)}</g>
          <g className="fleet-vehicle-markers">{visibleVehicles.map((vehicle, index) => {
            const color = fleetStatusMeta[vehicle.status].color;
            const isPriorityVehicle = selectedVehicle.id === vehicle.id
              || vehicle.id === originalVehicleId
              || vehicle.id === targetVehicleId
              || vehicle.status === "BROKEN"
              || vehicle.status === "DISPATCHING";
            const popupTransform = vehicle.x > 880
              ? "translate(-184 16)"
              : vehicle.y > 540
                ? "translate(26 -88)"
                : "translate(26 16)";
            return <g
              key={vehicle.id}
              role="button"
              tabIndex={0}
              aria-label={`${vehicle.id}，${fleetStatusMeta[vehicle.status].label}，${vehicle.locationLabel}`}
              data-fleet-vehicle-id={vehicle.id}
              data-fleet-status={vehicle.status}
              data-fleet-node-id={vehicle.nodeId}
              data-route-offset="0"
              data-map-priority={isPriorityVehicle ? "critical" : "background"}
              className={`fleet-vehicle-marker ${selectedVehicle.id === vehicle.id ? "is-selected" : ""}`}
              transform={`translate(${vehicle.x.toFixed(2)} ${vehicle.y.toFixed(2)})`}
              onClick={() => selectVehicle(vehicle.id)}
              onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") selectVehicle(vehicle.id); }}
            >
              <g className="fleet-vehicle-symbol">
                <circle className="vehicle-halo" r="20" fill={color}/>
                <path className="vehicle-body" fill={color} d="M-13-7H4V8H-13Z"/><path className="vehicle-cab" fill={color} d="M4-4H10L15 2V8H4Z"/>
                <path className="vehicle-window" d="M6-2H9L12 2H6Z"/><circle className="vehicle-wheel" cx="-8" cy="9" r="3"/><circle className="vehicle-wheel" cx="10" cy="9" r="3"/>
              </g>
              <g className="fleet-vehicle-label" transform={`translate(${index % 3 === 0 ? -24 : 18} -24)`}><rect x="-4" y="-13" width="58" height="22" rx="5"/><text x="25" y="2" textAnchor="middle">{vehicle.id}</text></g>
              {vehicle.status === "BROKEN" ? <g className="fleet-vehicle-alert" transform="translate(17 -16)"><circle r="10"/><text textAnchor="middle" y="4">!</text></g> : null}
              {selectedVehicle.id === vehicle.id ? <g className="fleet-selected-popup" transform={popupTransform}><rect x="0" y="0" width="158" height="65" rx="5"/><text className="popup-title" x="11" y="18">{vehicle.id} · {fleetStatusMeta[vehicle.status].label}</text><text x="11" y="35">速度 {vehicle.speedKph} km/h</text><text x="11" y="51">{vehicle.locationLabel}</text></g> : null}
            </g>;
          })}</g>
        </svg> : null}
        <div className="fleet-map-legend">{(Object.keys(fleetStatusMeta) as FleetVehicleStatus[]).map((status) => <span key={status}><i style={{ background: fleetStatusMeta[status].color }}/>{fleetStatusMeta[status].label}</span>)}<span className="is-hub-stop"><i/>仓储/调度中心</span><span className="is-station-stop"><i/>配送/快递/维修站</span><span className="is-service-stop"><i/>末端服务点</span><small>地图范围：嵩明县杨林物流走廊 · 22 个命名站点 · 33 段业务道路</small></div>
      </div>

      <aside className="fleet-vehicle-panel" aria-label="车辆信息">
        {operationSnapshot ? <VehicleOperationTimeline snapshot={operationSnapshot} context="dispatcher"/> : null}
        <section className="fleet-map-alert-card">
          <header><strong><AlertTriangle size={16}/>实时预警</strong><button type="button">查看全部</button></header>
          <div className="fleet-alert-tabs"><button type="button" className="is-active">全部 <b>{statusCounts.BROKEN + statusCounts.MAINTENANCE}</b></button><button type="button">异常停车</button><button type="button">路线偏离</button></div>
          <button type="button" className="fleet-alert-row is-critical" onClick={() => selectVehicle(selectedVehicle.id)}><AlertTriangle size={16}/><span><b>{selectedVehicle.id} · {fleetStatusMeta[selectedVehicle.status].label}</b><small>{selectedVehicle.locationLabel} · {selectedVehicle.speedKph} km/h</small></span><time>刚刚</time></button>
          <div className="fleet-alert-row"><Wrench size={16}/><span><b>{statusCounts.MAINTENANCE} 辆车正在维修</b><small>维修完成后自动质检并复岗</small></span><time>自动</time></div>
          <div className="fleet-alert-row"><MapPinned size={16}/><span><b>路线状态已同步</b><small>{blockedEdgeIds.size ? `${blockedEdgeIds.size} 个道路风险点` : "全县路网运行正常"}</small></span><time>实时</time></div>
        </section>
        <section className="fleet-map-stat-card">
          <header><strong><Truck size={16}/>车辆运行统计</strong></header>
          <div className="fleet-stat-content"><div className="fleet-stat-donut" style={{ background: `conic-gradient(#10b981 0 ${activeVehicleCount / 20 * 100}%, #3b82f6 ${activeVehicleCount / 20 * 100}% ${(activeVehicleCount + statusCounts.AVAILABLE) / 20 * 100}%, #ef4444 ${(activeVehicleCount + statusCounts.AVAILABLE) / 20 * 100}% 100%)` }}><span><b>20</b><small>总车辆</small></span></div><ul><li><i className="is-running"/>运行中 <b>{activeVehicleCount}</b></li><li><i className="is-idle"/>空闲 <b>{statusCounts.AVAILABLE}</b></li><li><i className="is-fault"/>异常/维修 <b>{statusCounts.BROKEN + statusCounts.MAINTENANCE}</b></li></ul></div>
        </section>
        <section className="fleet-mileage-ranking">
          <header><strong><TrendingUp size={16}/>今日里程排行</strong><button type="button">查看全部</button></header>
          <ol>{mileageRanking.map((vehicle, index) => <li key={vehicle.id}><em>{index + 1}</em><span>{vehicle.id}</span><i><b style={{ width: `${Math.max(26, vehicle.progress)}%` }}/></i><strong>{Math.round(92 + vehicle.progress * .72 + index * 4)} km</strong></li>)}</ol>
        </section>
        <div className="fleet-selected-vehicle">
          <p>当前选中车辆</p><h3>{selectedVehicle.id}</h3>
          <span className={`fleet-status-pill is-${selectedVehicle.status.toLowerCase()}`}>{fleetStatusMeta[selectedVehicle.status].label}</span>
          <dl>
            <div><dt>执行路线</dt><dd>{selectedRoute.displayId} · {selectedRoute.name}</dd></div>
            <div><dt>当前位置</dt><dd>{selectedVehicle.locationLabel}</dd></div>
            <div><dt>实时速度</dt><dd>{selectedVehicle.speedKph} 公里/小时</dd></div>
            <div><dt>当前载重</dt><dd>{selectedVehicle.loadKg} / {selectedVehicle.capacityKg} 千克</dd></div>
            <div><dt>路线进度</dt><dd>{selectedVehicle.progress}%</dd></div>
            <div><dt>下一站</dt><dd>{selectedTrip.nextStop}</dd></div>
            <div><dt>剩余距离</dt><dd>{selectedTrip.remainingKm} 公里</dd></div>
            <div><dt>预计到达</dt><dd>{selectedTrip.etaMinutes ? `${selectedTrip.etaMinutes} 分钟` : "等待调度"}</dd></div>
            {selectedOperationVehicle?.assigned_driver_id ? <div><dt>当前司机</dt><dd>{selectedOperationVehicle.assigned_driver_id}</dd></div> : null}
            {selectedOperationVehicle?.status_reason ? <div><dt>状态说明</dt><dd>{selectedOperationVehicle.status_reason}</dd></div> : null}
          </dl>
          <div className="fleet-progress"><i style={{ width: `${selectedVehicle.progress}%` }}/></div>
        </div>
        <div className="fleet-roster-heading"><strong>车辆清单</strong><span>{visibleVehicles.length} / 20</span></div>
        <div className="fleet-roster">{visibleVehicles.map((vehicle) => {
          const route = routeById.get(vehicle.routeId) ?? fleetRoutes[0];
          const node = nodeById.get(vehicle.nodeId) ?? fleetNodes[0];
          return <button type="button" key={vehicle.id} data-fleet-roster-id={vehicle.id} className={selectedVehicle.id === vehicle.id ? "is-selected" : ""} onClick={() => selectVehicle(vehicle.id)}>
            <i style={{ background: fleetStatusMeta[vehicle.status].color }}/><span><b>{vehicle.id}</b><small>{route.displayId} · {node.name}</small></span><em>{fleetStatusMeta[vehicle.status].label}</em>
          </button>;
        })}</div>
      </aside>
    </div>
    <footer className="fleet-command-footer" aria-label="车辆态势运营摘要">
      <article data-fleet-footer-metric="nodes"><MapPinned size={20}/><span><small>仓储与配送节点</small><strong>{fleetNodes.length}</strong></span></article>
      <article data-fleet-footer-metric="routes"><Route size={20}/><span><small>运营路线</small><strong>{fleetRoutes.length}</strong></span></article>
      <article data-fleet-footer-metric="mileage"><TrendingUp size={20}/><span><small>今日行驶里程</small><strong>{todayMileage.toLocaleString("zh-CN")} <em>km</em></strong></span></article>
      <article data-fleet-footer-metric="events"><Radio size={20}/><span><small>最新调度动态</small><strong>{events.length || (connection === "CONNECTED" ? "实时同步" : "等待连接")}</strong></span></article>
    </footer>
  </section>;
}
