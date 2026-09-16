import { describe, expect, it } from "vitest";

import {
  fleetRouteHeading,
  fleetRouteMotionProgress,
  fleetVehicleMapPointOffsets,
  fleetVehicleOverlapOffsets,
} from "../src/features/fleet-sandbox/fleet-motion-geometry";

describe("fleet motion geometry", () => {
  it("eases vehicles into route endpoints instead of reversing at full speed", () => {
    expect(fleetRouteMotionProgress(0)).toBe(0);
    expect(fleetRouteMotionProgress(0.5)).toBeCloseTo(0.5);
    expect(fleetRouteMotionProgress(1)).toBe(1);
    expect(fleetRouteMotionProgress(1.5)).toBeCloseTo(0.5);

    const startStep = fleetRouteMotionProgress(0.01) - fleetRouteMotionProgress(0);
    const middleStep = fleetRouteMotionProgress(0.51) - fleetRouteMotionProgress(0.5);
    const endStep = fleetRouteMotionProgress(1) - fleetRouteMotionProgress(0.99);
    expect(startStep).toBeLessThan(middleStep / 10);
    expect(endStep).toBeLessThan(middleStep / 10);
  });

  it("uses the road tangent and travel direction for vehicle heading", () => {
    const path = [[103, 25], [104, 25], [104, 26]] as const;
    expect(fleetRouteHeading(path, 0.25, 0.25)).toBeCloseTo(90);
    expect(fleetRouteHeading(path, 0.75, 0.75)).toBeCloseTo(0);
    expect(Math.abs(fleetRouteHeading(path, 0.25, 1.75))).toBeCloseTo(90);
  });

  it("assigns deterministic screen offsets only to vehicles occupying the same road point", () => {
    const offsets = fleetVehicleOverlapOffsets([
      { id: "V-001", routeId: "ROUTE-01", progress: 0.2, moving: false, nodeId: "N01" },
      { id: "V-002", routeId: "ROUTE-01", progress: 0.2, moving: false, nodeId: "N01" },
      { id: "V-003", routeId: "ROUTE-01", progress: 0.7, moving: true, nodeId: "N03" },
    ]);

    expect(offsets.get("V-001")).not.toEqual({ x: 0, y: 0 });
    expect(offsets.get("V-002")).not.toEqual(offsets.get("V-001"));
    const first = offsets.get("V-001")!;
    const second = offsets.get("V-002")!;
    expect(Math.hypot(first.x - second.x, first.y - second.y)).toBeGreaterThanOrEqual(64);
    expect(offsets.get("V-003")).toEqual({ x: 0, y: 0 });
  });

  it("keeps every rendered map marker apart after resolving neighbouring clusters", () => {
    const vehicles = [
      { id: "V-001", x: 0, y: 0 },
      { id: "V-002", x: 70, y: 0 },
      { id: "V-003", x: 100, y: 0 },
      { id: "V-004", x: 115, y: 45 },
    ];
    const offsets = fleetVehicleMapPointOffsets(vehicles);
    const renderedPoints = vehicles.map((vehicle) => {
      const offset = offsets.get(vehicle.id)!;
      return { id: vehicle.id, x: vehicle.x + offset.x, y: vehicle.y + offset.y };
    });

    for (let left = 0; left < renderedPoints.length; left += 1) {
      for (let right = left + 1; right < renderedPoints.length; right += 1) {
        expect(Math.hypot(
          renderedPoints[left].x - renderedPoints[right].x,
          renderedPoints[left].y - renderedPoints[right].y,
        )).toBeGreaterThanOrEqual(72);
      }
    }
  });

  it("keeps map markers outside floating control overlays", () => {
    const vehicles = [
      { id: "V-NORTH", x: 344, y: 47 },
      { id: "V-SOUTH", x: 1180, y: 670 },
    ];
    const offsets = fleetVehicleMapPointOffsets(
      vehicles,
      72,
      { minX: 230, maxX: 1110, minY: 92, maxY: 600 },
    );

    expect(vehicles[0].y + offsets.get("V-NORTH")!.y).toBeGreaterThanOrEqual(92);
    expect(vehicles[1].x + offsets.get("V-SOUTH")!.x).toBeLessThanOrEqual(1110);
    expect(vehicles[1].y + offsets.get("V-SOUTH")!.y).toBeLessThanOrEqual(600);
  });
});
