import {
  AlertTriangle,
  Check,
  CircleDot,
  Crosshair,
  Gauge,
  Layers3,
  Minus,
  Navigation,
  Plus,
  ShieldCheck,
  Truck,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
  OperationMapEdge,
  OperationMapNode,
  OperationRoute,
  VehicleOperationSnapshot,
} from "../types/vehicle-operations";


const routeMeta: Record<OperationRoute["kind"], { label: string; className: string }> = {
  REPLACEMENT: { label: "替代配送", className: "is-replacement" },
  RESCUE: { label: "救援路线", className: "is-rescue" },
  TOW: { label: "拖运路线", className: "is-tow" },
  INTERRUPTED: { label: "原路线中断", className: "is-interrupted" },
};

function clockLabel(seconds: number | null): string {
  if (seconds === null) return "待生成";
  const safe = Math.max(0, seconds);
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function timestampLabel(value: string): string {
  if (/^\d{2}:\d{2}$/.test(value)) return value;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function maintenanceDiagnosisLabel(snapshot: VehicleOperationSnapshot): string {
  if (snapshot.maintenance.status === "SCHEDULED" || snapshot.maintenance.status === "WAITING_BAY") {
    return "车辆到站后开始诊断";
  }
  return snapshot.maintenance.diagnosis ?? "维修人员正在确认故障原因";
}

function maintenanceAvailableLabel(snapshot: VehicleOperationSnapshot): string {
  return snapshot.maintenance.available_after
    ? timestampLabel(snapshot.maintenance.available_after)
    : "维修开始后生成";
}

function routeSegments(route: OperationRoute, edgeById: Map<string, OperationMapEdge>) {
  return route.edge_ids.map((edgeId) => edgeById.get(edgeId)).filter((edge): edge is OperationMapEdge => Boolean(edge));
}

export function VehicleCommandCenter({ snapshot, connection }: {
  snapshot: VehicleOperationSnapshot;
  connection: "CONNECTED" | "RECONNECTING";
}) {
  const [layer, setLayer] = useState<"TOPOLOGY" | "TRAFFIC" | "VEHICLES">("TOPOLOGY");
  const [zoom, setZoom] = useState(1);
  const [hiddenRoutes, setHiddenRoutes] = useState<Set<OperationRoute["kind"]>>(new Set());
  const [seconds, setSeconds] = useState(snapshot.maintenance.countdown_seconds);
  const recovered = snapshot.incident.status === "RECOVERED";
  const countdownActive = snapshot.maintenance.status !== "COMPLETED" && seconds !== null;

  useEffect(() => {
    const synchronization = window.setTimeout(
      () => setSeconds(snapshot.maintenance.countdown_seconds),
      0,
    );
    return () => window.clearTimeout(synchronization);
  }, [snapshot.maintenance.countdown_seconds]);
  useEffect(() => {
    if (!countdownActive) return undefined;
    const timer = window.setInterval(
      () => setSeconds((current) => current === null ? null : Math.max(0, current - 1)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [countdownActive]);

  const geometry = useMemo(() => {
    const xs = snapshot.nodes.map((node) => Number(node.x_km));
    const ys = snapshot.nodes.map((node) => Number(node.y_km));
    const minX = Math.min(...xs); const maxX = Math.max(...xs);
    const minY = Math.min(...ys); const maxY = Math.max(...ys);
    const point = (node: OperationMapNode) => ({
      x: 56 + ((Number(node.x_km) - minX) / Math.max(1, maxX - minX)) * 838,
      y: 70 + (1 - (Number(node.y_km) - minY) / Math.max(1, maxY - minY)) * 490,
    });
    return new Map(snapshot.nodes.map((node) => [node.node_id, { ...node, ...point(node) }]));
  }, [snapshot.nodes]);
  const edgeById = useMemo(() => new Map(snapshot.edges.map((edge) => [edge.edge_id, edge])), [snapshot.edges]);
  const majorNodes = new Set(["N01", "N04", "N05", "N06", "N08", "N11", "N13", "N14", "N15"]);

  const toggleRoute = (kind: OperationRoute["kind"]) => setHiddenRoutes((current) => {
    const next = new Set(current);
    if (next.has(kind)) next.delete(kind); else next.add(kind);
    return next;
  });

  return <section className="vehicle-command-center" aria-label="车辆救援维修地图指挥中心">
    <div className="vehicle-command-grid">
      <article className="operation-map-card">
        <header className="operation-map-header">
          <div>
            <p>新平县交通路网</p>
            <span>标准矢量底图 · 路况与业务图层已开启</span>
          </div>
          <nav aria-label="地图图层">
            <button type="button" className={layer === "TOPOLOGY" ? "is-active" : ""} onClick={() => setLayer("TOPOLOGY")}><Layers3 size={14}/>路网拓扑</button>
            <button type="button" className={layer === "TRAFFIC" ? "is-active" : ""} onClick={() => setLayer("TRAFFIC")}><Gauge size={14}/>实时路况</button>
            <button type="button" className={layer === "VEHICLES" ? "is-active" : ""} onClick={() => setLayer("VEHICLES")}><Truck size={14}/>车辆</button>
          </nav>
          <span className={`operation-live is-${connection.toLowerCase()}`}><i/>{connection === "CONNECTED" ? "实时路况" : "正在重连"}</span>
        </header>

        <div className="operation-map-viewport">
          <svg viewBox="0 0 950 600" role="img" aria-label="新平县真实路网、故障车辆、替代配送、救援与拖运路线">
            <rect width="950" height="600" className="operation-map-land"/>
            <path className="operation-map-river-bank" d="M-20 265 C145 215 230 320 395 285 S655 215 980 270"/>
            <path className="operation-map-river" d="M-20 269 C145 219 230 324 395 289 S655 219 980 274"/>
            <g className="operation-map-blocks" aria-hidden="true">
              {Array.from({ length: 34 }, (_, index) => <rect key={index} x={220 + (index % 9) * 67 + (index % 2) * 10} y={165 + Math.floor(index / 9) * 74} width={38 + index % 3 * 7} height={25 + index % 2 * 8} rx="3"/>)}
            </g>
            <g className="operation-map-network" transform={`translate(${475 * (1 - zoom)} ${300 * (1 - zoom)}) scale(${zoom})`}>
              <g className="operation-base-roads is-casing">
                {snapshot.edges.map((edge) => { const from = geometry.get(edge.from_node_id); const to = geometry.get(edge.to_node_id); return from && to ? <line key={edge.edge_id} x1={from.x} y1={from.y} x2={to.x} y2={to.y}/> : null; })}
              </g>
              <g className={`operation-base-roads is-surface layer-${layer.toLowerCase()}`}>
                {snapshot.edges.map((edge) => { const from = geometry.get(edge.from_node_id); const to = geometry.get(edge.to_node_id); return from && to ? <line key={edge.edge_id} className={`road-${edge.road_level.toLowerCase()}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y}/> : null; })}
              </g>
              {snapshot.routes.map((route) => <g key={route.kind} data-operation-route={route.kind} className={`operation-business-route ${routeMeta[route.kind].className} ${hiddenRoutes.has(route.kind) ? "is-hidden" : ""}`}>
                {routeSegments(route, edgeById).map((edge) => { const from = geometry.get(edge.from_node_id); const to = geometry.get(edge.to_node_id); return from && to ? <line key={edge.edge_id} x1={from.x} y1={from.y} x2={to.x} y2={to.y}/> : null; })}
              </g>)}
              <g className="operation-node-labels">
                {snapshot.nodes.filter((node) => majorNodes.has(node.node_id)).map((node) => { const point = geometry.get(node.node_id); return point ? <g key={node.node_id} transform={`translate(${point.x} ${point.y})`}><circle r="3"/><text x="8" y="-7">{node.name}</text></g> : null; })}
              </g>
              {snapshot.vehicles.filter((vehicle) => vehicle.is_incident || vehicle.is_replacement).map((vehicle) => { const point = geometry.get(vehicle.current_node_id); if (!point) return null; const incidentRecovered = vehicle.is_incident && recovered; return <g key={vehicle.vehicle_id} className={`operation-vehicle-marker ${incidentRecovered ? "is-recovered" : vehicle.is_incident ? "is-incident" : "is-replacement"}`} transform={`translate(${point.x} ${point.y})`}>
                <circle r="18"/><rect x="-9" y="-5" width="18" height="10" rx="2"/><circle cx="-5" cy="7" r="2.5"/><circle cx="6" cy="7" r="2.5"/>
                <g className="operation-marker-label" transform="translate(-42 -54)"><rect width="150" height="38" rx="7"/><text x="10" y="16">{vehicle.plate_no} · {incidentRecovered ? "已复岗" : vehicle.is_incident ? "故障" : "接管"}</text><text x="10" y="30">{incidentRecovered ? "维修质检完成 · 已恢复运营" : vehicle.is_incident ? "发动机异常 · 新平路 K3.2" : "陈师傅 · 冷链状态正常"}</text></g>
              </g>; })}
              {(() => { const point = geometry.get(snapshot.rescue.incident_node_id); const rescueStatus = snapshot.rescue.status === "DELIVERED" ? "已送达" : snapshot.rescue.status === "ARRIVED" ? "已抵达" : "行进中"; return point ? <g className="operation-rescue-marker" transform={`translate(${point.x + 65} ${point.y + 34})`}><circle r="17"/><path d="M-9 2h18M-5-5h10l4 7h-18z"/><text x="23" y="5">{snapshot.rescue.rescue_unit_id} · {rescueStatus}</text></g> : null; })()}
            </g>
            <text className="operation-water-label" x="68" y="283">青 水 河</text>
            <g className="operation-road-badge" transform="translate(644 218)"><rect width="46" height="22" rx="5"/><text x="23" y="15" textAnchor="middle">G102</text></g>
            <g className="operation-road-badge is-county" transform="translate(560 372) rotate(18)"><rect width="48" height="22" rx="5"/><text x="24" y="15" textAnchor="middle">X308</text></g>
          </svg>
          <div className="operation-map-controls" aria-label="地图缩放控制">
            <button type="button" aria-label="放大地图" onClick={() => setZoom((value) => Math.min(1.35, value + .1))}><Plus size={19}/></button>
            <button type="button" aria-label="缩小地图" onClick={() => setZoom((value) => Math.max(.75, value - .1))}><Minus size={19}/></button>
            <button type="button" aria-label="定位故障车辆" onClick={() => setZoom(1.2)}><Crosshair size={17}/></button>
          </div>
          <button type="button" className="operation-fit-view" aria-label="适配全景" onClick={() => setZoom(1)}><Crosshair size={14}/>全景视野</button>
          <div className="operation-scale"><i/>2 km</div>
          <div className="operation-route-legend" aria-label="业务路线图例">
            {snapshot.routes.map((route) => <button key={route.kind} type="button" className={`${routeMeta[route.kind].className} ${hiddenRoutes.has(route.kind) ? "is-off" : ""}`} onClick={() => toggleRoute(route.kind)}><i/>{routeMeta[route.kind].label}</button>)}
          </div>
        </div>
      </article>

      <VehicleOperationPanel snapshot={snapshot} countdown={clockLabel(seconds)} recovered={recovered}/>

      <footer className="operation-event-rail" aria-label="事件推进时间轴">
        {snapshot.timeline.slice(0, 4).map((event, index) => <div key={event.event_id} className="operation-event-item">
          <span>{timestampLabel(event.timestamp)}</span><strong>{event.label}</strong><small>{index === 0 ? "员工上报并停止行驶" : index === 1 ? "换车、救援与工位同步编排" : index === 2 ? `维修进度 ${snapshot.maintenance.progress_percent}%` : "维修与安检完成后自动恢复"}</small>
          {index < Math.min(3, snapshot.timeline.length - 1) ? <Navigation size={15}/> : null}
        </div>)}
      </footer>
    </div>
  </section>;
}

function VehicleOperationPanel({ snapshot, countdown, recovered }: { snapshot: VehicleOperationSnapshot; countdown: string; recovered: boolean }) {
  const incidentVehicle = snapshot.vehicles.find((vehicle) => vehicle.is_incident);
  return <aside className="operation-status-panel" aria-labelledby="operation-panel-title">
    <header>
      <div><p>事件处置</p><h2 id="operation-panel-title">{recovered ? "车辆故障 · 处置已完成" : "车辆故障 · 自动处置中"}</h2><span>任务 {snapshot.task_id} · 员工现场上报</span></div>
      <b className={recovered ? "is-recovered" : ""}>{recovered ? <ShieldCheck size={13}/> : <AlertTriangle size={13}/>} {recovered ? "已恢复" : "高风险"}</b>
    </header>
    <dl className="operation-incident-facts">
      <div><dt>故障车辆</dt><dd>{incidentVehicle?.plate_no ?? snapshot.incident.vehicle_id}</dd></div><div><dt>发生位置</dt><dd>{snapshot.incident.location_node_id}</dd></div>
      <div><dt>货物</dt><dd>{snapshot.incident.cargo}</dd></div><div><dt>安全状态</dt><dd className={recovered ? "is-recovered" : "is-danger"}>{recovered ? "已恢复运营" : "禁止继续行驶"}</dd></div>
    </dl>
    <div className="operation-stage-heading"><strong>自主处置编排</strong><span>4 个阶段 · 自动推进</span></div>
    <ol className="operation-stage-list">
      {snapshot.stages.map((stage, index) => <li key={stage.key} data-operation-stage={stage.key} className={`is-${stage.status.toLowerCase()}`}>
        <span>{stage.status === "COMPLETED" ? <Check size={15}/> : index + 1}</span>
        <div><strong>{stage.title}</strong><small>{stage.detail}</small></div>
        <b>{stage.status === "COMPLETED" ? "已完成" : stage.status === "ACTIVE" ? "进行中" : "待执行"}</b>
      </li>)}
    </ol>
    <section className="operation-maintenance-card">
      <header><span><Wrench size={15}/>维修工单</span><b>{snapshot.maintenance.order_no}</b></header>
      <dl><div><dt>维修工位</dt><dd>{snapshot.maintenance.bay_code ?? "待分配"}</dd></div><div><dt>故障诊断</dt><dd>{maintenanceDiagnosisLabel(snapshot)}</dd></div><div><dt>预计工时</dt><dd>{snapshot.maintenance.repair_minutes} 分钟</dd></div><div><dt>预计恢复</dt><dd>{maintenanceAvailableLabel(snapshot)}</dd></div></dl>
      <div className="operation-countdown"><span><CircleDot size={13}/>系统预计剩余时间</span><strong>{countdown}</strong></div>
      <div className="operation-progress"><i style={{ width: `${snapshot.maintenance.progress_percent}%` }}/></div>
      <small>当前维修进度 {snapshot.maintenance.progress_percent}%</small>
    </section>
    <div className="operation-auto-recovery"><ShieldCheck size={17}/><span><strong>{recovered ? "车辆已自动复岗" : "自动恢复条件"}</strong><small>{recovered ? "维修工单与安全检查均已完成，车辆可继续参与调度" : "工单完成 + 安全检查通过后，车辆自动恢复为可调度"}</small></span></div>
  </aside>;
}
