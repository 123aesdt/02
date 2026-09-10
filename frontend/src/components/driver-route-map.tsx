import { Gauge, MapPin, Navigation, Route as RouteIcon } from "lucide-react";

import { fleetRouteGeometry, fleetRoutePoints } from "../features/fleet-sandbox/fleet-map-geometry";
import { vehicleDisplayLabel } from "../features/fleet-sandbox/fleet-sandbox-data";
import { fleetNodeById } from "../features/fleet-sandbox/fleet-simulation";
import type { FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";

interface DriverRouteMapProps {
  vehicle: FleetPositionSnapshot;
}

export function DriverRouteMap({ vehicle }: DriverRouteMapProps) {
  const geometry = fleetRouteGeometry(vehicle.routeId, 85);
  const currentNodeIndex = Math.max(0, geometry.route.nodeIds.indexOf(vehicle.nodeId));
  const nextNodeId = geometry.route.nodeIds[Math.min(currentNodeIndex + 1, geometry.route.nodeIds.length - 1)];
  const nextNode = fleetNodeById.get(nextNodeId) ?? geometry.nodes.at(-1);
  const gridId = `driver-route-grid-${geometry.route.id}`;
  const vehicleLabel = vehicleDisplayLabel(vehicle.id);

  return <article className="driver-route-card" aria-labelledby="driver-route-map-title">
    <header>
      <div><p className="eyebrow">司机车辆实时位置</p><h3 id="driver-route-map-title">{vehicle.routeDisplayName}</h3></div>
      <strong><Navigation size={15}/>{vehicleLabel}</strong>
    </header>
    <div className="driver-route-map-shell">
      <svg
        data-driver-route-map
        data-route-id={geometry.route.id}
        viewBox={geometry.viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${vehicleLabel} 在 ${geometry.route.displayId} 的虚拟实时位置`}
      >
        <defs><pattern id={gridId} width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="currentColor" strokeWidth="1"/></pattern></defs>
        <rect className="driver-route-grid" x="0" y="0" width="1200" height="680" fill={`url(#${gridId})`}/>
        <g className="driver-route-roads">{geometry.edges.map((edge) => {
          const from = fleetNodeById.get(edge.from); const to = fleetNodeById.get(edge.to);
          return from && to ? <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y}/> : null;
        })}</g>
        <polyline data-driver-route-line points={fleetRoutePoints(geometry.route.id)} stroke={geometry.route.color}/>
        <g className="driver-route-stops">{geometry.nodes.map((node) => <g key={node.id} data-driver-stop-id={node.id} transform={`translate(${node.x} ${node.y})`}>
          <circle r={node.kind === "HUB" ? 11 : 7}/><text x="13" y="-3">{node.id}</text><text x="13" y="12">{node.name}</text>
        </g>)}</g>
        <g className="driver-current-vehicle" data-fleet-vehicle-id={vehicle.id} transform={`translate(${vehicle.x.toFixed(2)} ${vehicle.y.toFixed(2)})`}>
          <circle className="driver-vehicle-pulse" r="22"/><circle className="driver-vehicle-dot" r="11"/><text x="16" y="5">{vehicleLabel}</text>
        </g>
      </svg>
    </div>
    <dl className="driver-route-live-facts">
      <div><dt><MapPin size={14}/>当前位置</dt><dd>{vehicle.locationLabel}</dd></div>
      <div><dt><Navigation size={14}/>下一站</dt><dd>{nextNode?.name ?? "终点站"}</dd></div>
      <div><dt><Gauge size={14}/>当前速度</dt><dd>{vehicle.speedKph} 公里/小时</dd></div>
      <div><dt><RouteIcon size={14}/>路线进度</dt><dd>{vehicle.progress}%</dd></div>
    </dl>
  </article>;
}
