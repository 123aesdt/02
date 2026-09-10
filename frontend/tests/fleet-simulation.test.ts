import { describe, expect, it } from "vitest";

import { fleetRouteGeometry } from "../src/features/fleet-sandbox/fleet-map-geometry";
import { fleetSnapshotByVehicleId } from "../src/features/fleet-sandbox/fleet-simulation";

describe("fleet simulation vehicle identity", () => {
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
