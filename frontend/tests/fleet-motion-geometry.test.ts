import { describe, expect, it } from "vitest";

import {
  fleetRouteHeading,
  fleetRouteMotionProgress,
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
    expect(offsets.get("V-003")).toEqual({ x: 0, y: 0 });
  });
});
