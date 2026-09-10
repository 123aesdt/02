import type { RoutePlanResponse } from "../services/api/dispatch-adapter";

type EdgeState = "blocked" | "pickup" | "recommended" | "original" | "normal";

export interface RouteVehicleMarker {
  vehicleId: string;
  nodeId: string;
  state: "failed" | "moving";
  label: string;
  offsetX?: number;
}

const MAP_WIDTH = 960;
const MAP_HEIGHT = 360;
const MAP_PADDING_X = 48;
const MAP_PADDING_Y = 44;

function edgeState(edgeId: string, status: string, blocked: Set<string>, pickup: Set<string>, recommended: Set<string>, original: Set<string>): EdgeState {
  if (status.toUpperCase() === "BLOCKED" || blocked.has(edgeId)) return "blocked";
  if (pickup.has(edgeId)) return "pickup";
  if (recommended.has(edgeId)) return "recommended";
  if (original.has(edgeId)) return "original";
  return "normal";
}

const STATE_LABELS: Readonly<Record<EdgeState, string>> = {
  blocked: "堵塞道路",
  pickup: "接驳路线",
  recommended: "重新规划路线",
  original: "原路线",
  normal: "普通道路",
};

function finiteCoordinate(value: string): number | null {
  const coordinate = Number(value);
  return Number.isFinite(coordinate) ? coordinate : null;
}

export function RouteVisual({ routePlan, pickupEdgeIds = [], compact = false, vehicleMarkers = [] }: { routePlan: RoutePlanResponse | null; pickupEdgeIds?: string[]; compact?: boolean; vehicleMarkers?: RouteVehicleMarker[] }) {
  const validNodes = (routePlan?.network_nodes ?? []).flatMap((node) => {
    const x = finiteCoordinate(node.x_km);
    const y = finiteCoordinate(node.y_km);
    return x === null || y === null ? [] : [{ ...node, x, y }];
  });
  const validNodeIds = new Set(validNodes.map((node) => node.node_id));
  const edgeById = new Map<string, RoutePlanResponse["network_edges"][number]>();
  for (const edge of routePlan?.network_edges ?? []) {
    if (validNodeIds.has(edge.from_node_id) && validNodeIds.has(edge.to_node_id) && !edgeById.has(edge.edge_id)) edgeById.set(edge.edge_id, edge);
  }
  const validEdges = [...edgeById.values()];
  if (!validNodes.length || !validEdges.length) {
    return <div className={`route-visual route-visual-empty ${compact ? "route-visual-compact" : ""}`}><p>暂无可绘制的道路网络</p></div>;
  }

  const xValues = validNodes.map((node) => node.x);
  const yValues = validNodes.map((node) => node.y);
  const minX = Math.min(...xValues);
  const minY = Math.min(...yValues);
  const maxX = Math.max(...xValues);
  const maxY = Math.max(...yValues);
  const xSpan = Math.max(maxX - minX, 1);
  const ySpan = Math.max(maxY - minY, 1);
  const positionedNodes = validNodes.map((node) => ({
    ...node,
    x: MAP_PADDING_X + ((node.x - minX) / xSpan) * (MAP_WIDTH - MAP_PADDING_X * 2),
    y: MAP_HEIGHT - MAP_PADDING_Y - ((node.y - minY) / ySpan) * (MAP_HEIGHT - MAP_PADDING_Y * 2),
  }));
  const nodeById = new Map(positionedNodes.map((node) => [node.node_id, node]));
  const blocked = new Set(routePlan?.blocked_edge_ids ?? []);
  const pickup = new Set(pickupEdgeIds);
  const recommended = new Set(routePlan?.recommended_path?.edge_ids ?? []);
  const original = new Set(routePlan?.original_path?.edge_ids ?? []);

  return <div className={`route-visual route-visual-api ${compact ? "route-visual-compact" : ""}`}>
    <svg viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} role="img" aria-label="根据接口节点坐标计算的县域道路与调度路线">
      <g className="road-network">{validEdges.map((edge) => {
        const from = nodeById.get(edge.from_node_id)!;
        const to = nodeById.get(edge.to_node_id)!;
        const state = edgeState(edge.edge_id, edge.status, blocked, pickup, recommended, original);
        return <g key={edge.edge_id} data-edge-id={edge.edge_id} data-route-state={state} className={`road-edge route-${state}`}>
          <title>{edge.name} · {STATE_LABELS[state]} · {edge.distance_km} 公里</title>
          <line x1={from.x} y1={from.y} x2={to.x} y2={to.y}/>
        </g>;
      })}</g>
      <g className="network-nodes">{positionedNodes.map((node) => {
        const placeLabelOnLeft = node.x > MAP_WIDTH * .76;
        const placeLabelBelow = node.y < MAP_PADDING_Y + 24;
        const labelX = node.x + (placeLabelOnLeft ? -11 : 11);
        const labelY = node.y + (placeLabelBelow ? 18 : -8);
        const isNamedSite = node.node_type.toUpperCase() === "DEPOT" || node.node_type.toUpperCase() === "STATION";
        return <g key={node.node_id} data-node-id={node.node_id} className={`network-node node-${node.node_type.toLowerCase()}`}>
        <title>{node.name} · {node.node_id}</title>
        <circle cx={node.x} cy={node.y} r={compact ? 5 : 7}/>
        {compact ? null : <g className="network-node-label" textAnchor={placeLabelOnLeft ? "end" : "start"}>
          <text className="network-node-code" x={labelX} y={labelY}>{node.node_id}</text>
          {isNamedSite ? <text className="network-node-name" x={labelX} y={labelY + (placeLabelBelow ? 12 : 13)}>{node.name}</text> : null}
        </g>}
      </g>})}</g>
      <g className="vehicle-markers">{vehicleMarkers.flatMap((marker) => {
        const node = nodeById.get(marker.nodeId);
        if (!node) return [];
        return [<g
          key={`${marker.vehicleId}-${marker.state}`}
          className={`vehicle-map-marker is-${marker.state}`}
          data-vehicle-id={marker.vehicleId}
          data-node-id={marker.nodeId}
          data-vehicle-state={marker.state}
          transform={`translate(${node.x + (marker.offsetX ?? 0)} ${node.y})`}
          role="img"
          aria-label={marker.label}
        >
          <title>{marker.label} · 当前节点 {marker.nodeId}</title>
          <circle className="vehicle-marker-halo" cx="0" cy="0" r="20"/>
          <g className="vehicle-marker-glyph" aria-hidden="true">
            <rect x="-13" y="-8" width="19" height="13" rx="3"/>
            <path d="M6 -4h5l5 6v3H6z"/>
            <circle cx="-7" cy="7" r="3"/>
            <circle cx="11" cy="7" r="3"/>
          </g>
          <text className="vehicle-marker-label" x="0" y="-25" textAnchor="middle">{marker.label}</text>
        </g>];
      })}</g>
    </svg>
  </div>;
}
