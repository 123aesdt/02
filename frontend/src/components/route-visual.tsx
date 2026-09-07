import type { RoutePlanResponse } from "../services/api/dispatch-adapter";

type EdgeState = "blocked" | "pickup" | "recommended" | "original" | "normal";

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

export function RouteVisual({ routePlan, pickupEdgeIds = [], compact = false }: { routePlan: RoutePlanResponse | null; pickupEdgeIds?: string[]; compact?: boolean }) {
  const validNodes = (routePlan?.network_nodes ?? []).flatMap((node) => {
    const x = finiteCoordinate(node.x_km);
    const y = finiteCoordinate(node.y_km);
    return x === null || y === null ? [] : [{ ...node, x, y }];
  });
  const nodeById = new Map(validNodes.map((node) => [node.node_id, node]));
  const edgeById = new Map<string, RoutePlanResponse["network_edges"][number]>();
  for (const edge of routePlan?.network_edges ?? []) {
    if (nodeById.has(edge.from_node_id) && nodeById.has(edge.to_node_id) && !edgeById.has(edge.edge_id)) edgeById.set(edge.edge_id, edge);
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
  const padding = 1;
  const viewBox = `${minX - padding} ${minY - padding} ${maxX - minX + padding * 2} ${maxY - minY + padding * 2}`;
  const blocked = new Set(routePlan?.blocked_edge_ids ?? []);
  const pickup = new Set(pickupEdgeIds);
  const recommended = new Set(routePlan?.recommended_path?.edge_ids ?? []);
  const original = new Set(routePlan?.original_path?.edge_ids ?? []);

  return <div className={`route-visual route-visual-api ${compact ? "route-visual-compact" : ""}`}>
    <svg viewBox={viewBox} role="img" aria-label="根据接口节点坐标计算的县域道路与调度路线">
      <g className="road-network">{validEdges.map((edge) => {
        const from = nodeById.get(edge.from_node_id)!;
        const to = nodeById.get(edge.to_node_id)!;
        const state = edgeState(edge.edge_id, edge.status, blocked, pickup, recommended, original);
        return <g key={edge.edge_id} data-edge-id={edge.edge_id} data-route-state={state} className={`road-edge route-${state}`}>
          <title>{edge.name} · {STATE_LABELS[state]} · {edge.distance_km} 公里</title>
          <line x1={from.x} y1={from.y} x2={to.x} y2={to.y}/>
        </g>;
      })}</g>
      <g className="network-nodes">{validNodes.map((node) => <g key={node.node_id} data-node-id={node.node_id} className={`network-node node-${node.node_type.toLowerCase()}`}>
        <title>{node.name} · {node.node_id}</title>
        <circle cx={node.x} cy={node.y} r={compact ? 1.4 : 1.8}/>
        {compact ? null : <text x={node.x + 2.2} y={node.y - 2.2}>{node.name}</text>}
      </g>)}</g>
    </svg>
  </div>;
}
