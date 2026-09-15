import { fleetRouteLngLatPath } from "./fleet-amap-coordinates";
import { fleetNodeById } from "./fleet-simulation";
import type { FleetRoute } from "./fleet-sandbox-data";
import type { FleetPositionSnapshot } from "./fleet-simulation";
import type { OperationRoute, VehicleOperationSnapshot } from "../../types/vehicle-operations";

export interface FleetOperationRouteSpec {
  id: string;
  kind: Exclude<OperationRoute["kind"], "INTERRUPTED">;
  nodeIds: string[];
  status: string;
  color: string;
}

const operationRouteMeta = {
  REPLACEMENT: { id: "OP-REPLACEMENT", color: "#16a36a" },
  RESCUE: { id: "OP-RESCUE", color: "#f59e0b" },
  TOW: { id: "OP-TOW", color: "#ef5b4d" },
} as const;

function progressToDeadline(snapshot: VehicleOperationSnapshot, durationSeconds: number, referenceTimeMs?: number): number {
  if (!snapshot.rescue.next_transition_at) return 0;
  const generatedAt = referenceTimeMs ?? new Date(snapshot.generated_at).getTime();
  const deadline = new Date(snapshot.rescue.next_transition_at).getTime();
  if (!Number.isFinite(generatedAt) || !Number.isFinite(deadline)) return 0;
  return Math.max(0, Math.min(1, 1 - (deadline - generatedAt) / (durationSeconds * 1000)));
}

export function fleetOperationRouteSpecs(snapshot: VehicleOperationSnapshot | null | undefined): FleetOperationRouteSpec[] {
  if (!snapshot) return [];
  return snapshot.routes.flatMap((route) => {
    if (route.kind === "INTERRUPTED" || route.node_ids.length < 2) return [];
    const meta = operationRouteMeta[route.kind];
    return [{ id: meta.id, kind: route.kind, nodeIds: route.node_ids, status: route.status, color: meta.color }];
  });
}

export function fleetRescueUnitPresentation(snapshot: VehicleOperationSnapshot | null | undefined, referenceTimeMs?: number) {
  if (!snapshot) return null;
  if (snapshot.rescue.status === "DISPATCHED") {
    return {
      routeId: "OP-RESCUE",
      progress: progressToDeadline(snapshot, 8, referenceTimeMs),
      label: "前往故障点",
      unitId: snapshot.rescue.rescue_unit_id,
    };
  }
  if (snapshot.rescue.status === "LOADED") {
    return {
      routeId: "OP-TOW",
      progress: progressToDeadline(snapshot, 4, referenceTimeMs),
      label: "拖往维修站",
      unitId: snapshot.rescue.rescue_unit_id,
    };
  }
  return {
    routeId: snapshot.rescue.status === "DELIVERED" ? "OP-TOW" : "OP-RESCUE",
    progress: 1,
    label: snapshot.rescue.status === "DELIVERED" ? "已到维修站" : "已到故障点",
    unitId: snapshot.rescue.rescue_unit_id,
  };
}

function routeDistanceKm(route: FleetRoute): number {
  const points = fleetRouteLngLatPath(route);
  return points.slice(0, -1).reduce((total, point, index) => {
    const next = points[index + 1];
    const averageLatitude = (point[1] + next[1]) / 2 * Math.PI / 180;
    const eastKm = (next[0] - point[0]) * 111.32 * Math.cos(averageLatitude);
    const northKm = (next[1] - point[1]) * 110.57;
    return total + Math.hypot(eastKm, northKm);
  }, 0);
}

export function fleetVehicleTripDetails(vehicle: FleetPositionSnapshot, route: FleetRoute) {
  const wrappedPhase = ((vehicle.routePhase % 2) + 2) % 2;
  const forward = wrappedPhase <= 1;
  const routeIndex = Math.max(0, Math.min(route.nodeIds.length - 1, Math.round(vehicle.routeProgress * (route.nodeIds.length - 1))));
  const nextIndex = Math.max(0, Math.min(route.nodeIds.length - 1, routeIndex + (forward ? 1 : -1)));
  const nextNode = fleetNodeById.get(route.nodeIds[nextIndex]);
  const totalKm = routeDistanceKm(route);
  const remainingKm = totalKm * (forward ? 1 - vehicle.routeProgress : vehicle.routeProgress);
  return {
    nextStop: nextNode?.name ?? "等待调度",
    remainingKm: Number(Math.max(0, remainingKm).toFixed(1)),
    etaMinutes: vehicle.speedKph > 0 ? Math.max(1, Math.ceil(remainingKm / vehicle.speedKph * 60)) : 0,
  };
}
