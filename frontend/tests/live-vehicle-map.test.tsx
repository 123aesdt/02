import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

import { LiveVehicleMap } from "../src/components/live-vehicle-map";
import type { RoutePlanResponse, VehicleAllocationResponse } from "../src/services/api/dispatch-adapter";
import type { TaskEvent } from "../src/types/task-events";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const node = (node_id: string, name: string, x_km: string, y_km: string, node_type = "JUNCTION") => ({ node_id, name, x_km, y_km, node_type });
const edge = (edge_id: string, from_node_id: string, to_node_id: string) => ({ edge_id, name: `道路${edge_id}`, from_node_id, to_node_id, distance_km: "2.00", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 });

const routePlan: RoutePlanResponse = {
  original_path: { objective: "FASTEST", node_ids: ["N04", "N06"], edge_ids: ["E05"], distance_km: "5.00", estimated_minutes: 10, risk_cost: "0.80", visited_node_count: 2, scoring_formula: null },
  recommended_path: { objective: "FASTEST", node_ids: ["N04", "N08", "N06"], edge_ids: ["E21", "E09"], distance_km: "7.20", estimated_minutes: 14, risk_cost: "0.20", visited_node_count: 4, scoring_formula: "ROUTE_SCORE_V1" },
  candidate_routes: [], blocked_edge_ids: ["E05"], distance_delta_km: "2.20", eta_delta_minutes: 4, visited_node_count: 4, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 7,
  network_nodes: [node("N04", "故障上报点", "5.00", "2.00", "INCIDENT_POINT"), node("N15", "县域车辆维修站", "4.00", "1.00", "STATION"), node("N08", "102 国道中段", "6.00", "-2.00"), node("N06", "城东配送站", "10.00", "2.00", "STATION")],
  network_edges: [edge("E20", "N15", "N04"), edge("E05", "N04", "N06"), edge("E21", "N04", "N08"), edge("E09", "N08", "N06")],
};

const allocation: VehicleAllocationResponse = {
  original_vehicle_id: "V-001", target_vehicle_id: "V-005", target_driver_id: "D-003", vehicle_reassigned: true, scoring_formula: "FLEET_SCORE_V1",
  pickup_route: { objective: "FASTEST", node_ids: ["N15", "N04"], edge_ids: ["E20"], distance_km: "2.80", estimated_minutes: 6, risk_cost: "0.10", visited_node_count: 2, scoring_formula: null },
  candidate_vehicles: [],
};

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

it("keeps the failed vehicle red while the replacement vehicle advances every 1.5 seconds", async () => {
  vi.useFakeTimers();
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<LiveVehicleMap anomalyType="VEHICLE_BREAKDOWN" allocation={allocation} routePlan={routePlan} connection="CONNECTED" />); });

  expect(container.textContent).toContain("虚拟沙盘实时模拟");
  expect(container.textContent).toContain("V-001 · 故障车辆");
  expect(container.textContent).toContain("V-005 · 已派出");
  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-node-id")).toBe("N04");
  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-vehicle-state")).toBe("failed");
  expect(container.querySelector('[data-vehicle-id="V-005"]')?.getAttribute("data-node-id")).toBe("N15");

  await act(async () => { vi.advanceTimersByTime(1500); });
  expect(container.querySelector('[data-vehicle-id="V-005"]')?.getAttribute("data-node-id")).toBe("N04");
  expect(container.textContent).toContain("已到达接驳点");

  const pause = [...container.querySelectorAll("button")].find((button) => button.textContent === "暂停模拟");
  await act(async () => { pause?.click(); vi.advanceTimersByTime(3000); });
  expect(container.querySelector('[data-vehicle-id="V-005"]')?.getAttribute("data-node-id")).toBe("N04");
  await act(async () => { root.unmount(); });
});

it("moves the active vehicle along the recalculated route for a road blockage", async () => {
  vi.useFakeTimers();
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<LiveVehicleMap anomalyType="ROAD_BLOCKED" allocation={{ ...allocation, target_vehicle_id: null, target_driver_id: null, vehicle_reassigned: false, pickup_route: null }} routePlan={routePlan} connection="CONNECTED" />); });

  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-node-id")).toBe("N04");
  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-vehicle-state")).toBe("moving");
  expect(container.querySelector('[data-vehicle-id="V-005"]')).toBeNull();
  await act(async () => { vi.advanceTimersByTime(1500); });
  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-node-id")).toBe("N08");
  await act(async () => { root.unmount(); });
});

it("renders the reported failure and dispatch result directly from live Agent events before the terminal result refresh", async () => {
  const taskEvent = (event_type: string, nodeName: string, sequence: number, data: Record<string, unknown>): TaskEvent => ({ event_id: `${sequence}`, task_id: "TASK-LIVE", event_type, node: nodeName, status: "PROCESSING", timestamp: "2026-09-09T10:00:00Z", sequence, data });
  const events = [
    taskEvent("CAPACITY_COMPLETED", "capacity", 1, { vehicle_id: "V-001", vehicle_status: "BROKEN", selected_vehicle_id: "V-005", selected_driver_id: "D-003", vehicle_reassigned: true, pickup_route: allocation.pickup_route }),
    taskEvent("ROUTING_COMPLETED", "routing", 2, routePlan as unknown as Record<string, unknown>),
  ];
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<LiveVehicleMap anomalyType="VEHICLE_BREAKDOWN" allocation={null} routePlan={null} connection="CONNECTED" events={events} />); });

  expect(container.querySelector('[data-vehicle-id="V-001"]')?.getAttribute("data-vehicle-state")).toBe("failed");
  expect(container.querySelector('[data-vehicle-id="V-005"]')?.getAttribute("data-node-id")).toBe("N15");
  expect(container.textContent).toContain("已同步 2 个 Agent 实时事件");
  await act(async () => { root.unmount(); });
});
