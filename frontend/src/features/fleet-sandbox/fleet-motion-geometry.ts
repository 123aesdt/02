interface FleetOverlapCandidate {
  id: string;
  routeId: string;
  progress: number;
  moving: boolean;
  nodeId: string;
}

export interface FleetVehicleScreenOffset {
  x: number;
  y: number;
}

export function fleetRouteMotionProgress(phase: number): number {
  const wrapped = ((phase % 2) + 2) % 2;
  const linearProgress = wrapped <= 1 ? wrapped : 2 - wrapped;
  return (1 - Math.cos(Math.PI * linearProgress)) / 2;
}

function pathSegmentAt(
  path: ReadonlyArray<readonly [number, number]>,
  progress: number,
): { from: readonly [number, number]; to: readonly [number, number] } | null {
  if (path.length < 2) return null;
  const segments = path.slice(0, -1).map((from, index) => ({
    from,
    to: path[index + 1],
    length: Math.hypot(path[index + 1][0] - from[0], path[index + 1][1] - from[1]),
  }));
  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0);
  if (!totalLength) return null;
  const safeProgress = Number.isFinite(progress) ? progress : 0;
  let remaining = Math.max(0, Math.min(1, safeProgress)) * totalLength;
  return segments.find((segment) => {
    if (remaining <= segment.length) return true;
    remaining -= segment.length;
    return false;
  }) ?? segments.at(-1)!;
}

export function fleetRouteHeading(
  path: ReadonlyArray<readonly [number, number]>,
  progress: number,
  phase: number,
): number {
  const segment = pathSegmentAt(path, progress);
  if (!segment) return 0;
  const averageLatitude = (segment.from[1] + segment.to[1]) / 2 * Math.PI / 180;
  const east = (segment.to[0] - segment.from[0]) * Math.cos(averageLatitude);
  const north = segment.to[1] - segment.from[1];
  const forwardHeading = Math.atan2(east, north) * 180 / Math.PI;
  const safePhase = Number.isFinite(phase) ? phase : 0;
  const wrappedPhase = ((safePhase % 2) + 2) % 2;
  const directedHeading = forwardHeading + (wrappedPhase > 1 ? 180 : 0);
  return ((directedHeading + 540) % 360) - 180;
}

export function fleetVehicleOverlapOffsets(
  vehicles: ReadonlyArray<FleetOverlapCandidate>,
): Map<string, FleetVehicleScreenOffset> {
  const clusters = new Map<string, FleetOverlapCandidate[]>();
  for (const vehicle of vehicles) {
    const locationKey = vehicle.moving
      ? `${vehicle.routeId}:road:${Math.round(vehicle.progress * 240)}`
      : `${vehicle.routeId}:node:${vehicle.nodeId}`;
    const cluster = clusters.get(locationKey) ?? [];
    cluster.push(vehicle);
    clusters.set(locationKey, cluster);
  }

  const offsets = new Map<string, FleetVehicleScreenOffset>();
  for (const cluster of clusters.values()) {
    const ordered = [...cluster].sort((left, right) => left.id.localeCompare(right.id));
    if (ordered.length === 1) {
      offsets.set(ordered[0].id, { x: 0, y: 0 });
      continue;
    }
    const radius = ordered.length > 4 ? 48 : ordered.length > 2 ? 40 : 32;
    ordered.forEach((vehicle, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ordered.length;
      offsets.set(vehicle.id, {
        x: Math.round(Math.cos(angle) * radius),
        y: Math.round(Math.sin(angle) * radius),
      });
    });
  }
  return offsets;
}
