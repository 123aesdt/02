import { fleetEdges, fleetNodes, fleetRoutes } from "./fleet-sandbox-data";
import { fleetNodeById, fleetRouteById } from "./fleet-simulation";

function edgeKey(from: string, to: string): string {
  return [from, to].sort().join(":");
}

export function fleetRouteGeometry(routeId: string, padding = 70) {
  const route = fleetRouteById.get(routeId) ?? fleetRoutes[0];
  const nodes = route.nodeIds
    .map((nodeId) => fleetNodeById.get(nodeId))
    .filter((node): node is NonNullable<typeof node> => Boolean(node));
  const routeEdgeKeys = new Set(route.nodeIds.slice(0, -1).map((nodeId, index) => edgeKey(nodeId, route.nodeIds[index + 1])));
  const edges = fleetEdges.filter((edge) => routeEdgeKeys.has(edgeKey(edge.from, edge.to)));
  const minX = Math.min(route.labelX - 115, ...nodes.map((node) => node.x));
  const maxX = Math.max(route.labelX + 115, ...nodes.map((node) => node.x));
  const minY = Math.min(route.labelY - 22, ...nodes.map((node) => node.y));
  const maxY = Math.max(route.labelY + 22, ...nodes.map((node) => node.y));
  const x = Math.max(0, minX - padding);
  const y = Math.max(0, minY - padding);
  const width = Math.min(1200 - x, Math.max(360, maxX - minX + padding * 2));
  const height = Math.min(680 - y, Math.max(280, maxY - minY + padding * 2));

  return {
    route,
    nodes,
    edges,
    nodeIds: new Set(route.nodeIds),
    edgeIds: new Set(edges.map((edge) => edge.id)),
    viewBox: `${x} ${y} ${width} ${height}`,
  };
}

export function fleetRoutePoints(routeId: string): string {
  return fleetRouteGeometry(routeId, 0).nodes.map((node) => `${node.x},${node.y}`).join(" ");
}
function curvedEdge(edge: (typeof fleetEdges)[number]) {
  const from = fleetNodeById.get(edge.from);
  const to = fleetNodeById.get(edge.to);
  if (!from || !to) return null;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const sequence = Number(edge.id.replace(/\D/g, "")) || 1;
  const bend = Math.min(34, length * .14) * (sequence % 2 === 0 ? 1 : -1);
  return {
    from,
    to,
    controlX: (from.x + to.x) / 2 - dy / length * bend,
    controlY: (from.y + to.y) / 2 + dx / length * bend,
  };
}

export function fleetEdgePath(edge: (typeof fleetEdges)[number]): string {
  const curve = curvedEdge(edge);
  return curve ? `M ${curve.from.x} ${curve.from.y} Q ${curve.controlX.toFixed(1)} ${curve.controlY.toFixed(1)} ${curve.to.x} ${curve.to.y}` : "";
}

export function fleetRoutePath(routeId: string): string {
  const route = fleetRouteById.get(routeId) ?? fleetRoutes[0];
  const first = fleetNodeById.get(route.nodeIds[0]);
  if (!first) return "";
  return route.nodeIds.slice(1).reduce((path, nodeId, index) => {
    const previousId = route.nodeIds[index];
    const next = fleetNodeById.get(nodeId);
    if (!next) return path;
    const edge = fleetEdges.find((candidate) => edgeKey(candidate.from, candidate.to) === edgeKey(previousId, nodeId));
    const curve = edge ? curvedEdge(edge) : null;
    return curve
      ? `${path} Q ${curve.controlX.toFixed(1)} ${curve.controlY.toFixed(1)} ${next.x} ${next.y}`
      : `${path} L ${next.x} ${next.y}`;
  }, `M ${first.x} ${first.y}`);
}

export const fullFleetMapViewBox = "0 0 1200 680";

export const allFleetMapNodes = fleetNodes;
