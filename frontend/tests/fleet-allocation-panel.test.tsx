import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { FleetAllocationPanel } from "../src/components/fleet-allocation-panel";
import type { VehicleAllocationResponse } from "../src/services/api/dispatch-adapter";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => document.body.replaceChildren());

const allocation: VehicleAllocationResponse = {
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
    { vehicle_id: "县配测试车-X9", driver_id: "D-009", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY", remaining_capacity_kg: "850.00", gross_weight_tons: "2.50", cargo_capability: "COLD_CHAIN", pickup_route: { objective: "FASTEST", node_ids: ["N12", "N04"], edge_ids: ["E19"], distance_km: "3.10", estimated_minutes: 7, risk_cost: "0.20", visited_node_count: 3, scoring_formula: null }, pickup_distance_km: "3.10", pickup_eta_minutes: 7, score: "93.4", score_components: { eta_penalty: "4.0", distance_penalty: "1.6", load_penalty: "2.1", road_risk_penalty: "0.4", same_station_bonus: "1.0", cargo_exact_match_bonus: "3.0" }, scoring_formula: "FLEET_SCORE_V1", eligible: true, exclusion_reasons: [] },
  ],
};

async function renderPanel() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<FleetAllocationPanel allocation={allocation}/>); });
  return { container, root };
}

it("shows the failed vehicle, selected replacement, transfer, score, and every candidate reason", async () => {
  const { container, root } = await renderPanel();

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
  expect(container.querySelectorAll("[data-vehicle-id]")).toHaveLength(4);
  await act(async () => { root.unmount(); });
});

it("uses only API identities and keeps eligible non-selected candidates neutral", async () => {
  const { container, root } = await renderPanel();
  const unknownVehicle = container.querySelector('[data-vehicle-id="县配测试车-X9"]');

  expect(unknownVehicle?.getAttribute("aria-label")).toBe("县配测试车-X9 候选车辆");
  expect(container.textContent).not.toContain("新物冷链");
  expect(unknownVehicle?.textContent).toContain("满足硬约束");
  expect(unknownVehicle?.textContent).not.toContain("综合评分低于入选车辆");
  expect(container.textContent).not.toContain("综合评分最高");
  await act(async () => { root.unmount(); });
});

it("renders a semantic candidate table with complete evidence for every vehicle", async () => {
  const { container, root } = await renderPanel();
  const table = container.querySelector("table");
  const selectedRow = container.querySelector('[data-vehicle-id="V-005"]');
  const peerRow = container.querySelector('[data-vehicle-id="县配测试车-X9"]');
  const excludedRow = container.querySelector('[data-vehicle-id="V-001"]');

  expect(table?.querySelector("caption")?.textContent).toContain("车辆候选证据表");
  expect(table?.querySelector("thead")).not.toBeNull();
  expect(table?.querySelector("tbody")).not.toBeNull();
  expect(table?.querySelectorAll('thead th[scope="col"]')).toHaveLength(11);
  expect(selectedRow?.querySelector('th[scope="row"]')?.textContent).toBe("V-005");
  expect(selectedRow?.querySelector('[data-field="driver"]')?.textContent).toContain("D-003");
  expect(selectedRow?.querySelector('[data-field="driver"]')?.textContent).toContain("在岗");
  expect(selectedRow?.querySelector('[data-field="pickup-distance"]')?.textContent).toBe("2.80 公里");
  expect(selectedRow?.querySelector('[data-field="pickup-eta"]')?.textContent).toBe("6 分钟");
  expect(selectedRow?.querySelector('[data-field="score"]')?.textContent).toBe("93.4");
  expect(selectedRow?.querySelector('[data-field="score-components"]')?.textContent).toContain("接驳时间扣分3.0");
  expect(selectedRow?.querySelector('[data-field="score-components"]')?.textContent).toContain("货物能力匹配加分3.0");
  expect(peerRow?.querySelector('[data-field="pickup-distance"]')?.textContent).toBe("3.10 公里");
  expect(peerRow?.querySelector('[data-field="pickup-eta"]')?.textContent).toBe("7 分钟");
  expect(peerRow?.querySelector('[data-field="score-components"]')?.textContent).toContain("道路风险扣分0.4");
  expect(excludedRow?.querySelector('[data-field="pickup-distance"]')?.textContent).toBe("未提供");
  expect(excludedRow?.querySelector('[data-field="score-components"]')?.textContent).toBe("未提供");
  await act(async () => { root.unmount(); });
});

it("shows candidate totals and a deterministic ranking for dispatchable replacement vehicles", async () => {
  const { container, root } = await renderPanel();
  const selectedCard = container.querySelector(".fleet-transfer-card.is-selected");
  const tableRows = [...container.querySelectorAll<HTMLTableRowElement>(".fleet-candidate-table tbody tr")];
  const selectedRow = container.querySelector('[data-vehicle-id="V-005"]');
  const peerRow = container.querySelector('[data-vehicle-id="县配测试车-X9"]');

  expect(container.querySelector(".fleet-candidate-heading")?.textContent).toContain("候选 4 辆 · 可调度 2 辆 · 已排除 2 辆");
  expect(selectedCard?.textContent).toContain("综合排名第 1");
  expect(tableRows.slice(0, 2).map((row) => row.dataset.vehicleId)).toEqual(["V-005", "县配测试车-X9"]);
  expect(selectedRow?.querySelector('[data-field="rank"]')?.textContent).toBe("第 1 名");
  expect(peerRow?.querySelector('[data-field="rank"]')?.textContent).toBe("第 2 名");
  expect(container.querySelector('[data-vehicle-id="V-001"] [data-field="rank"]')?.textContent).toBe("—");
  await act(async () => { root.unmount(); });
});
it("states clearly when no replacement vehicle or pickup route is available", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<FleetAllocationPanel allocation={{
    ...allocation,
    target_vehicle_id: null,
    target_driver_id: null,
    vehicle_reassigned: false,
    pickup_route: null,
    candidate_vehicles: allocation.candidate_vehicles.map((candidate) => ({ ...candidate, eligible: false })),
  }}/>); });

  expect(container.querySelector(".fleet-transfer")?.textContent).toContain("无可用接替车辆");
  expect(container.querySelector(".fleet-transfer")?.textContent).not.toContain("等待接驳路线");
  await act(async () => { root.unmount(); });
});
