import { describe, expect, it } from "vitest";

import { fleetRoutes, fleetVehicles } from "../src/features/fleet-sandbox/fleet-sandbox-data";
import {
  fleetOperationRouteSpecs,
  fleetRescueUnitPresentation,
  fleetVehicleTripDetails,
} from "../src/features/fleet-sandbox/fleet-operation-presentation";
import { fleetPositionForVehicle } from "../src/features/fleet-sandbox/fleet-simulation";
import type { VehicleOperationSnapshot } from "../src/types/vehicle-operations";

function operationSnapshot(status: "DISPATCHED" | "LOADED"): VehicleOperationSnapshot {
  return {
    task_id: "TASK-FAULT",
    generated_at: status === "DISPATCHED" ? "2026-09-11T10:00:04Z" : "2026-09-11T10:00:12Z",
    incident: {
      status: "AUTO_PROCESSING",
      risk: "HIGH",
      vehicle_id: "V-001",
      replacement_vehicle_id: "V-005",
      location_node_id: "N04",
      fault_code: "ENGINE_COOLING",
      cargo: "冷链生鲜 · 700kg",
    },
    nodes: [],
    edges: [],
    vehicles: [],
    routes: [
      { kind: "REPLACEMENT", edge_ids: ["E21", "E03", "E04"], node_ids: ["N15", "N19", "N01", "N03", "N04"], status: "ACTIVE" },
      { kind: "RESCUE", edge_ids: ["E22", "E04"], node_ids: ["N22", "N03", "N04"], status },
      { kind: "TOW", edge_ids: ["E20"], node_ids: ["N04", "N15"], status },
      { kind: "INTERRUPTED", edge_ids: ["E04"], node_ids: ["N03", "N04"], status: "INTERRUPTED" },
    ],
    rescue: {
      mission_no: "JY-001",
      status,
      progress_percent: status === "DISPATCHED" ? 25 : 75,
      rescue_unit_id: "救援-02",
      incident_node_id: "N04",
      station_node_id: "N15",
      next_transition_at: status === "DISPATCHED" ? "2026-09-11T10:00:08Z" : "2026-09-11T10:00:14Z",
    },
    maintenance: {
      order_no: "WX-001",
      vehicle_id: "V-001",
      bay_code: "A-02",
      status: "SCHEDULED",
      fault_code: "ENGINE_COOLING",
      diagnosis: "发动机冷却系统故障",
      repair_minutes: 120,
      manual_inspection_required: false,
      inspection_result: null,
      progress_percent: 0,
      countdown_seconds: 43,
      available_after: "2026-09-11T10:00:55Z",
    },
    stages: [],
    timeline: [],
  };
}

describe("fleet operation map presentation", () => {
  it("keeps backend ordered nodes for the three active operation routes", () => {
    const routes = fleetOperationRouteSpecs(operationSnapshot("DISPATCHED"));
    expect(routes.map((route) => route.id)).toEqual(["OP-REPLACEMENT", "OP-RESCUE", "OP-TOW"]);
    expect(routes[0].nodeIds).toEqual(["N15", "N19", "N01", "N03", "N04"]);
  });

  it("moves the rescue unit along outbound and towing routes using server deadlines", () => {
    const outbound = fleetRescueUnitPresentation(operationSnapshot("DISPATCHED"));
    expect(outbound).toMatchObject({ routeId: "OP-RESCUE", label: "前往故障点" });
    expect(outbound?.progress).toBeCloseTo(0.5);

    const towing = fleetRescueUnitPresentation(operationSnapshot("LOADED"));
    expect(towing).toMatchObject({ routeId: "OP-TOW", label: "拖往维修站" });
    expect(towing?.progress).toBeCloseTo(0.5);
  });

  it("calculates the next stop, remaining distance and ETA for live vehicle details", () => {
    const vehicle = fleetPositionForVehicle(fleetVehicles[1], 20);
    const details = fleetVehicleTripDetails(vehicle, fleetRoutes[0]);
    expect(details.nextStop.length).toBeGreaterThan(0);
    expect(details.remainingKm).toBeGreaterThan(0);
    expect(details.etaMinutes).toBeGreaterThan(0);
  });
});
