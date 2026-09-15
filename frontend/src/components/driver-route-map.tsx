import { Gauge, LocateFixed, Map as MapIcon, MapPin, Navigation, Route as RouteIcon, Satellite } from "lucide-react";
import { useState } from "react";

import { runtimeConfig } from "../config/runtime";
import { fleetRouteGeometry, fleetRoutePoints } from "../features/fleet-sandbox/fleet-map-geometry";
import { fleetVehicleTripDetails } from "../features/fleet-sandbox/fleet-operation-presentation";
import { vehicleDisplayLabel } from "../features/fleet-sandbox/fleet-sandbox-data";
import { fleetNodeById } from "../features/fleet-sandbox/fleet-simulation";
import type { FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";
import { AmapFleetMap, type AmapLoadState } from "./amap-fleet-map";

interface DriverRouteMapProps {
  vehicle: FleetPositionSnapshot;
}

export function DriverRouteMap({ vehicle }: DriverRouteMapProps) {
  const geometry = fleetRouteGeometry(vehicle.routeId, 85);
  const trip = fleetVehicleTripDetails(vehicle, geometry.route);
  const gridId = `driver-route-grid-${geometry.route.id}`;
  const vehicleLabel = vehicleDisplayLabel(vehicle.id);
  const amapEnabled = Boolean(runtimeConfig.amap?.enabled);
  const [mapMode, setMapMode] = useState<"STANDARD" | "SATELLITE">("SATELLITE");
  const [resetSequence, setResetSequence] = useState(0);
  const [amapState, setAmapState] = useState<AmapLoadState>(amapEnabled ? "LOADING" : "FALLBACK");

  return <article className="driver-route-card" aria-labelledby="driver-route-map-title">
    <header>
      <div><p className="eyebrow">司机车辆实时位置</p><h3 id="driver-route-map-title">{vehicle.routeDisplayName}</h3></div>
      <div className="driver-route-map-actions">
        <span className={`driver-map-source is-${amapState.toLowerCase()}`}>{amapState === "READY" ? "高德真实道路" : amapState === "LOADING" ? "道路匹配中" : "本地路线降级"}</span>
        {amapEnabled ? <button type="button" title={mapMode === "SATELLITE" ? "切换标准地图" : "切换卫星地图"} aria-label={mapMode === "SATELLITE" ? "切换标准地图" : "切换卫星地图"} onClick={() => setMapMode((value) => value === "SATELLITE" ? "STANDARD" : "SATELLITE")}>
          {mapMode === "SATELLITE" ? <MapIcon size={16}/> : <Satellite size={16}/>}
        </button> : null}
        {amapEnabled ? <button type="button" title="复位路线视野" aria-label="复位路线视野" onClick={() => setResetSequence((value) => value + 1)}><LocateFixed size={16}/></button> : null}
        <strong><Navigation size={15}/>{vehicleLabel}</strong>
      </div>
    </header>
    <div
      className={`driver-route-map-shell is-${mapMode.toLowerCase()}`}
      data-driver-route-map
      data-route-id={geometry.route.id}
      data-route-node-ids={geometry.route.nodeIds.join(",")}
      data-current-vehicle-id={vehicle.id}
      data-map-contract="AMAP_ROAD_V1"
      data-map-provider={amapEnabled ? "AMAP" : "LOCAL_FALLBACK"}
    >
      <svg
        className="driver-route-fallback-map"
        viewBox={geometry.viewBox}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${vehicleLabel} 在 ${geometry.route.displayId} 的路线位置`}
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
      {amapEnabled ? <AmapFleetMap
        apiKey={runtimeConfig.amap.key}
        securityCode={runtimeConfig.amap.securityCode}
        vehicles={[vehicle]}
        playing
        routeIds={[geometry.route.id]}
        roadPlanningRouteIds={[geometry.route.id]}
        nodeIds={geometry.route.nodeIds}
        criticalRouteIds={[geometry.route.id]}
        selectedVehicleId={vehicle.id}
        blockedEdgeIds={[]}
        mapMode={mapMode}
        perspective={false}
        zoom={1}
        resetSequence={resetSequence}
        followVehicle={false}
        showLabels
        showRoutes
        showNodes
        showRiskAreas={false}
        showTraffic={false}
        geofenceMode={false}
        onFollowChange={() => undefined}
        onVehicleSelect={() => undefined}
        onRouteSelect={() => undefined}
        onStateChange={setAmapState}
      /> : null}
      <div className="driver-route-map-legend" aria-hidden="true">
        <span><i className="is-route"/>当前配送路线</span>
        <span><i className="is-vehicle"/>当前车辆</span>
        <span><i className="is-station"/>沿线站点</span>
      </div>
    </div>
    <dl className="driver-route-live-facts">
      <div><dt><MapPin size={14}/>当前位置</dt><dd>{vehicle.locationLabel}</dd></div>
      <div><dt><Navigation size={14}/>下一站</dt><dd>{trip.nextStop}</dd></div>
      <div><dt><Gauge size={14}/>当前速度</dt><dd>{vehicle.speedKph} 公里/小时</dd></div>
      <div><dt><RouteIcon size={14}/>路线进度</dt><dd>{vehicle.progress}%</dd></div>
    </dl>
  </article>;
}
