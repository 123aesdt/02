import { describe, expect, it } from "vitest";

import { fleetRouteGeometry } from "../src/features/fleet-sandbox/fleet-map-geometry";
import { fleetRouteProgressForPhase, fleetSimulationTick, fleetSnapshotByVehicleId } from "../src/features/fleet-sandbox/fleet-simulation";

describe("fleet simulation vehicle identity", () => {
  it("keeps fractional simulation time for continuous vehicle motion", () => {
    expect(fleetSimulationTick(750)).toBe(0.5);
    expect(fleetSimulationTick(1875)).toBe(1.25);
  });

  it("turns vehicles around continuously at route endpoints", () => {
    expect(fleetRouteProgressForPhase(0.99)).toBeCloseTo(0.99);
    expect(fleetRouteProgressForPhase(1)).toBe(1);
    expect(fleetRouteProgressForPhase(1.01)).toBeCloseTo(0.99);
    expect(fleetRouteProgressForPhase(2)).toBe(0);
  });

  it.each([
    ["V-008", "V-008"],
    ["demo-vehicle-008", "V-008"],
    ["vehicle-001", "V-001"],
  ])("maps %s to the canonical sandbox vehicle %s", (sourceId, expectedId) => {
    expect(fleetSnapshotByVehicleId(sourceId, 0)?.id).toBe(expectedId);
  });

  it("does not invent a sandbox vehicle for an unknown identifier", () => {
    expect(fleetSnapshotByVehicleId("truck-without-number", 0)).toBeNull();
  });

  it("keeps the selected route name inside the zoomed map view", () => {
    const geometry = fleetRouteGeometry("ROUTE-07", 70);
    const [x, y, width, height] = geometry.viewBox.split(" ").map(Number);

    expect(geometry.route.labelX).toBeGreaterThanOrEqual(x);
    expect(geometry.route.labelX).toBeLessThanOrEqual(x + width);
    expect(geometry.route.labelY).toBeGreaterThanOrEqual(y);
    expect(geometry.route.labelY).toBeLessThanOrEqual(y + height);
  });
});
