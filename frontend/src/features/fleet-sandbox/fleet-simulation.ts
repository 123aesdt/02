import {
  fleetNodes,
  fleetRoutes,
  fleetVehicles,
  type FleetVehicle,
} from "./fleet-sandbox-data";
import { fleetRouteMotionProgress } from "./fleet-motion-geometry";

export interface FleetPositionSnapshot extends FleetVehicle {
  x: number;
  y: number;
  nodeId: string;
  locationLabel: string;
  progress: number;
  routeProgress: number;
  routePhase: number;
  routeDisplayName: string;
}

export const fleetNodeById = new Map(fleetNodes.map((node) => [node.id, node]));
export const fleetRouteById = new Map(fleetRoutes.map((route) => [route.id, route]));

export function fleetSimulationTick(timeMs = Date.now()): number {
  return timeMs / 1500;
}

export function fleetRouteProgressForPhase(phase: number): number {
  const wrappedPhase = ((phase % 2) + 2) % 2;
  return wrappedPhase <= 1 ? wrappedPhase : 2 - wrappedPhase;
}

export function canonicalFleetVehicleId(vehicleId: string | null | undefined): string | null {
  if (!vehicleId) return null;
  const normalized = vehicleId.trim().toUpperCase();
  if (fleetVehicles.some((vehicle) => vehicle.id === normalized)) return normalized;
  const suffix = normalized.match(/(?:^|[-_])(?:V|VEHICLE)[-_]?0*(\d{1,3})$/)?.[1];
  if (!suffix) return null;
  const sequence = Number(suffix);
  if (sequence < 1 || sequence > fleetVehicles.length) return null;
  return `V-${String(sequence).padStart(3, "0")}`;
}

function pointAlongRoute(routeId: string, progress: number) {
  const route = fleetRouteById.get(routeId) ?? fleetRoutes[0];
  const points = route.nodeIds.map((nodeId) => fleetNodeById.get(nodeId)).filter((node): node is NonNullable<typeof node> => Boolean(node));
  const segments = points.slice(0, -1).map((point, index) => ({
    from: point,
    to: points[index + 1],
    length: Math.hypot(points[index + 1].x - point.x, points[index + 1].y - point.y),
  }));
  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0);
  const wrappedProgress = ((progress % 1) + 1) % 1;
  let remaining = wrappedProgress * totalLength;
  const segment = segments.find((candidate) => {
    if (remaining <= candidate.length) return true;
    remaining -= candidate.length;
    return false;
  }) ?? segments.at(-1);
  if (!segment) return { x: points[0]?.x ?? 0, y: points[0]?.y ?? 0, startNodeId: route.nodeIds[0], endNodeId: route.nodeIds[0], segmentProgress: 0 };
  const segmentProgress = segment.length ? Math.min(1, remaining / segment.length) : 0;
  return {
    x: segment.from.x + (segment.to.x - segment.from.x) * segmentProgress,
    y: segment.from.y + (segment.to.y - segment.from.y) * segmentProgress,
    startNodeId: segment.from.id,
    endNodeId: segment.to.id,
    segmentProgress,
  };
}

export function fleetPositionForVehicle(vehicle: FleetVehicle, tick: number): FleetPositionSnapshot {
  const vehicleIndex = fleetVehicles.findIndex((candidate) => candidate.id === vehicle.id);
  const safeIndex = vehicleIndex < 0 ? 0 : vehicleIndex;
  const route = fleetRouteById.get(vehicle.routeId) ?? fleetRoutes[0];
  const isMoving = vehicle.status === "IN_TRANSIT" || vehicle.status === "DISPATCHING";
  const fixedStep = vehicle.initialStep % route.nodeIds.length;
  const pairSlot = safeIndex % 2;
  const routeIndex = Math.floor(safeIndex / 2);
  const startingProgress = ((pairSlot === 0 ? 0.16 : 0.62) + (routeIndex % 3) * 0.035) % 1;
  const routePhase = isMoving
    ? (startingProgress + tick * 0.006 * Math.max(vehicle.speedKph, 30) / 40) % 2
    : fixedStep / Math.max(1, route.nodeIds.length - 1);
  const progressValue = fleetRouteMotionProgress(routePhase);
  const routePosition = isMoving ? pointAlongRoute(vehicle.routeId, progressValue) : null;
  const fixedNodeId = route.nodeIds[fixedStep];
  const fixedNode = fleetNodeById.get(fixedNodeId) ?? fleetNodes[0];
  const nearestNodeId = routePosition
    ? routePosition.segmentProgress < 0.5 ? routePosition.startNodeId : routePosition.endNodeId
    : fixedNodeId;
  const startNode = routePosition ? fleetNodeById.get(routePosition.startNodeId) : null;
  const endNode = routePosition ? fleetNodeById.get(routePosition.endNodeId) : null;
  const locationLabel = routePosition && startNode && endNode
    ? routePosition.segmentProgress < 0.12 ? startNode.name : routePosition.segmentProgress > 0.88 ? endNode.name : `${startNode.name}—${endNode.name}路段`
    : fixedNode.name;
  const routeProgress = isMoving
    ? progressValue
    : fixedStep / Math.max(1, route.nodeIds.length - 1);
  return {
    ...vehicle,
    nodeId: nearestNodeId,
    progress: Math.round(routeProgress * 100),
    routeProgress,
    routePhase,
    x: routePosition?.x ?? fixedNode.x,
    y: routePosition?.y ?? fixedNode.y,
    locationLabel,
    routeDisplayName: `${route.displayId} · ${route.name}`,
  };
}

export function fleetSnapshotByVehicleId(vehicleId: string | null | undefined, tick: number): FleetPositionSnapshot | null {
  const canonicalId = canonicalFleetVehicleId(vehicleId);
  const vehicle = fleetVehicles.find((candidate) => candidate.id === canonicalId);
  return vehicle ? fleetPositionForVehicle(vehicle, tick) : null;
}
