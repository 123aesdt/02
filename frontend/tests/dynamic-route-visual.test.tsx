import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { RouteVisual } from "../src/components/route-visual";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => document.body.replaceChildren());

const nodes = [
  { node_id: "N01", name: "中心仓", x_km: "0.00", y_km: "0.00", node_type: "DEPOT" },
  { node_id: "N02", name: "北门", x_km: "2.00", y_km: "0.00", node_type: "JUNCTION" },
  { node_id: "N03", name: "东河桥", x_km: "4.00", y_km: "0.00", node_type: "JUNCTION" },
  { node_id: "N04", name: "绕行口", x_km: "2.00", y_km: "2.00", node_type: "JUNCTION" },
  { node_id: "N05", name: "城东站", x_km: "5.00", y_km: "1.00", node_type: "STATION" },
];
const edge = (edge_id: string, name: string, from_node_id: string, to_node_id: string, status = "OPEN") => ({ edge_id, name, from_node_id, to_node_id, distance_km: "2.00", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status, congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 });

it("draws each API edge once and applies blocked, pickup, recommended, then original priority", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<RouteVisual pickupEdgeIds={["E20", "E07"]} routePlan={{
    original_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N03", "N05"], edge_ids: ["E01", "E04", "E05"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "1.00", visited_node_count: 6, scoring_formula: null },
    recommended_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N04", "N05"], edge_ids: ["E01", "E07", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0.40", visited_node_count: 8, scoring_formula: "ROUTE_SCORE_V1" },
    candidate_routes: [], blocked_edge_ids: ["E04"], distance_delta_km: "3.20", eta_delta_minutes: 4, visited_node_count: 8, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 7,
    network_nodes: nodes,
    network_edges: [edge("E01", "仓前路", "N01", "N02"), edge("E04", "新平路东河桥段", "N02", "N03", "BLOCKED"), edge("E05", "新平路东段", "N03", "N05"), edge("E07", "北环支路", "N02", "N04"), edge("E07", "重复的北环支路", "N02", "N04"), edge("E09", "城东联络线", "N04", "N05"), edge("E20", "维修站接驳线", "N04", "N05")],
  }}/>) });
  expect(container.querySelector("svg")?.getAttribute("viewBox")).toBe("0 0 960 360");
  expect(container.querySelectorAll("[data-edge-id]")).toHaveLength(6);
  expect(container.querySelector('[data-edge-id="E04"]')?.getAttribute("data-route-state")).toBe("blocked");
  expect(container.querySelector('[data-edge-id="E07"]')?.getAttribute("data-route-state")).toBe("pickup");
  expect(container.querySelector('[data-edge-id="E09"]')?.getAttribute("data-route-state")).toBe("recommended");
  expect(container.querySelector('[data-edge-id="E01"]')?.getAttribute("data-route-state")).toBe("recommended");
  expect(container.querySelector('[data-edge-id="E05"]')?.getAttribute("data-route-state")).toBe("original");
  expect(container.querySelector('[data-edge-id="E04"] title')?.textContent).toContain("新平路东河桥段");
  expect(container.querySelector('[data-edge-id="E04"]')?.hasAttribute("d")).toBe(false);
  await act(async () => { root.unmount(); });
});

it("renders a stable empty state when path evidence is absent", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<RouteVisual routePlan={{ original_path: null, recommended_path: null, candidate_routes: [], blocked_edge_ids: [], distance_delta_km: null, eta_delta_minutes: null, visited_node_count: null, routing_status: null, algorithm: "DIJKSTRA_V1", road_network_version: 7, network_nodes: [], network_edges: [] }}/>) });
  expect(container.textContent).toContain("暂无可绘制的道路网络");
  await act(async () => { root.unmount(); });
});
