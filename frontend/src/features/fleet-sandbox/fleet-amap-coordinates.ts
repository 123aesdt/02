import type { FleetMapNode, FleetRoute } from "./fleet-sandbox-data";
import { fleetNodeById } from "./fleet-simulation";

export type FleetLngLat = [number, number];

export const SONGMING_AMAP_BOUNDS = {
  west: 102.95,
  east: 103.17,
  south: 25.14,
  north: 25.315,
} as const;

export const SONGMING_AMAP_CENTER: FleetLngLat = [103.07, 25.23];

const nodeLngLatById: Readonly<Record<string, FleetLngLat>> = {
  N01: [103.0448, 25.2265],
  N02: [103.032, 25.232],
  N03: [103.057, 25.239],
  N04: [103.079, 25.246],
  N05: [103.104, 25.252],
  N06: [103.135, 25.261],
  N07: [103.018, 25.207],
  N08: [103.062, 25.198],
  N09: [103.105, 25.214],
  N10: [103.025, 25.267],
  N11: [103.013, 25.303],
  N12: [102.973, 25.247],
  N13: [103.072, 25.158],
  N14: [102.991, 25.217],
  N15: [103.077, 25.228],
  N16: [102.997, 25.279],
  N17: [103.132, 25.293],
  N18: [103.151, 25.204],
  N19: [103.051, 25.22],
  N20: [103.092, 25.235],
  N21: [103.117, 25.225],
  N22: [103.069, 25.231],
};

function roundCoordinate(value: number): number {
  return Number(value.toFixed(6));
}

export function fleetPointLngLat(x: number, y: number): FleetLngLat {
  const horizontalProgress = Math.max(0, Math.min(1, x / 1200));
  const verticalProgress = Math.max(0, Math.min(1, y / 680));
  return [
    roundCoordinate(SONGMING_AMAP_BOUNDS.west + horizontalProgress * (SONGMING_AMAP_BOUNDS.east - SONGMING_AMAP_BOUNDS.west)),
    roundCoordinate(SONGMING_AMAP_BOUNDS.north - verticalProgress * (SONGMING_AMAP_BOUNDS.north - SONGMING_AMAP_BOUNDS.south)),
  ];
}

export function fleetNodeLngLat(node: FleetMapNode): FleetLngLat {
  return nodeLngLatById[node.id] ?? fleetPointLngLat(node.x, node.y);
}

export function fleetRouteLngLatPath(route: FleetRoute): FleetLngLat[] {
  return route.nodeIds
    .map((nodeId) => fleetNodeById.get(nodeId))
    .filter((node): node is FleetMapNode => Boolean(node))
    .map(fleetNodeLngLat);
}

export function pointAlongLngLatPath(path: ReadonlyArray<readonly [number, number]>, progress: number): FleetLngLat {
  if (!path.length) return SONGMING_AMAP_CENTER;
  if (path.length === 1) return [...path[0]];
  const segments = path.slice(0, -1).map((point, index) => ({
    from: point,
    to: path[index + 1],
    length: Math.hypot(path[index + 1][0] - point[0], path[index + 1][1] - point[1]),
  }));
  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0);
  if (!totalLength) return [...path[0]];
  const safeProgress = Number.isFinite(progress) ? progress : 0;
  let remaining = Math.max(0, Math.min(1, safeProgress)) * totalLength;
  const segment = segments.find((candidate) => {
    if (remaining <= candidate.length) return true;
    remaining -= candidate.length;
    return false;
  }) ?? segments.at(-1)!;
  const segmentProgress = segment.length ? Math.min(1, remaining / segment.length) : 0;
  return [
    roundCoordinate(segment.from[0] + (segment.to[0] - segment.from[0]) * segmentProgress),
    roundCoordinate(segment.from[1] + (segment.to[1] - segment.from[1]) * segmentProgress),
  ];
}

export function closestPointOnLngLatPath(
  path: ReadonlyArray<readonly [number, number]>,
  target: readonly [number, number],
): FleetLngLat {
  if (!path.length) return Number.isFinite(target[0]) && Number.isFinite(target[1]) ? [...target] : SONGMING_AMAP_CENTER;
  if (path.length === 1) return [...path[0]];
  const safeTarget: readonly [number, number] = Number.isFinite(target[0]) && Number.isFinite(target[1])
    ? target
    : path[0];
  let closest: FleetLngLat = [...path[0]];
  let closestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < path.length - 1; index += 1) {
    const from = path[index];
    const to = path[index + 1];
    const dx = to[0] - from[0];
    const dy = to[1] - from[1];
    const lengthSquared = dx * dx + dy * dy;
    const projection = lengthSquared
      ? Math.max(0, Math.min(1, ((safeTarget[0] - from[0]) * dx + (safeTarget[1] - from[1]) * dy) / lengthSquared))
      : 0;
    const candidate: FleetLngLat = [from[0] + dx * projection, from[1] + dy * projection];
    const distance = Math.hypot(safeTarget[0] - candidate[0], safeTarget[1] - candidate[1]);
    if (distance < closestDistance) {
      closestDistance = distance;
      closest = candidate;
    }
  }
  return [roundCoordinate(closest[0]), roundCoordinate(closest[1])];
}
