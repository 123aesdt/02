import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { FleetAllocationPanel } from "../src/components/fleet-allocation-panel";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => document.body.replaceChildren());

it("shows the failed vehicle, selected replacement, transfer, score, and every candidate reason", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<FleetAllocationPanel allocation={{
      original_vehicle_id: "V-001",
      target_vehicle_id: "V-005",
      target_driver_id: "D-003",
      vehicle_reassigned: true,
      scoring_formula: "FLEET_SCORE_V1",
      pickup_route: { objective: "FASTEST", node_ids: ["N15", "N04"], edge_ids: ["E20"], distance_km: "2.80", estimated_minutes: 6, risk_cost: "0.10", visited_node_count: 2, scoring_formula: null },
      candidate_vehicles: [
        { vehicle_id: "V-001", driver_id: "D-001", vehicle_status: "BROKEN", driver_status: "ON_DUTY", remaining_capacity_kg: "800.00", gross_weight_tons: "2.80", cargo_capability: "COLD_CHAIN", pickup_route: null, pickup_distance_km: null, pickup_eta_minutes: null, score: null, score_components: null, scoring_formula: null, eligible: false, exclusion_reasons: ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"] },
        { vehicle_id: "V-002", driver_id: "D-002", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY", remaining_capacity_kg: "1000.00", gross_weight_tons: "2.20", cargo_capability: "GENERAL", pickup_route: null, pickup_distance_km: null, pickup_eta_minutes: null, score: null, score_components: null, scoring_formula: null, eligible: false, exclusion_reasons: ["CARGO_CAPABILITY_MISMATCH"] },
        { vehicle_id: "V-005", driver_id: "D-003", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY", remaining_capacity_kg: "900.00", gross_weight_tons: "2.40", cargo_capability: "COLD_CHAIN", pickup_route: { objective: "FASTEST", node_ids: ["N15", "N04"], edge_ids: ["E20"], distance_km: "2.80", estimated_minutes: 6, risk_cost: "0.10", visited_node_count: 2, scoring_formula: null }, pickup_distance_km: "2.80", pickup_eta_minutes: 6, score: "93.4", score_components: { eta_penalty: "3.0", distance_penalty: "1.4", load_penalty: "2.0", road_risk_penalty: "0.2", same_station_bonus: "0.0", cargo_exact_match_bonus: "3.0" }, scoring_formula: "FLEET_SCORE_V1", eligible: true, exclusion_reasons: [] },
      ],
    }}/>);
  });

  expect(container.textContent).toContain("故障车辆");
  expect(container.textContent).toContain("V-001");
  expect(container.textContent).toContain("接替车辆");
  expect(container.textContent).toContain("V-005");
  expect(container.textContent).toContain("D-003");
  expect(container.textContent).toContain("接驳 2.80 公里 · 6 分钟");
  expect(container.textContent).toContain("93.4");
  expect(container.textContent).toContain("原故障车辆不参与候选");
  expect(container.textContent).toContain("车辆当前不可用");
  expect(container.textContent).toContain("冷链能力不匹配");
  expect(container.querySelectorAll("[data-vehicle-id]")).toHaveLength(3);
  expect(container.querySelector('[data-vehicle-id="V-005"]')?.getAttribute("aria-label")).toContain("新物冷链-05");
  await act(async () => { root.unmount(); });
});
