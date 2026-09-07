import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { AuditEvidencePanel } from "../src/components/audit-evidence-panel";
import { RoutingEvidencePanel } from "../src/components/routing-evidence-panel";
import { RoutePlanResultPanel } from "../src/components/route-plan-result-panel";
import type { TaskEvent } from "../src/types/task-events";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
afterEach(() => document.body.replaceChildren());

function event(eventType: string, data: Record<string, unknown>): TaskEvent {
  return { event_id: eventType, task_id: "TASK-1", event_type: eventType, node: eventType.startsWith("ROUTING") ? "routing" : "audit", status: "PROCESSING", timestamp: "2026-08-27T00:00:03Z", sequence: 1, data };
}

it("renders backend routing candidates, exclusions, reason, and final decision", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<RoutingEvidencePanel events={[event("ROUTING_COMPLETED", { recommended_route: "national-102", decision: "REVIEW_REQUIRED", decision_reason: "Vehicle capacity unavailable", requires_manual_review: true, candidate_routes: [{ route_id: "national-102", route_name: "102国道", available: true, score: 92, reason: null }, { route_id: "xinping-road", route_name: "新平路", available: false, score: 0, reason: "Vehicle A — BROKEN" }] })]}/>); });

  expect(container.textContent).toContain("候选路线");
  expect(container.textContent).toContain("已排除资源");
  expect(container.textContent).toContain("车辆 A — 故障");
  expect(container.textContent).toContain("需要复核");
  expect(container.textContent).toContain("车辆运力不可用");
});


it("renders the persisted Dijkstra reroute calculation and dynamic network evidence", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  const edge = (edge_id: string, from_node_id: string, to_node_id: string, status = "OPEN") => ({ edge_id, name: `道路${edge_id}`, from_node_id, to_node_id, distance_km: "2.00", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status, congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 });
  await act(async () => { root.render(<RoutePlanResultPanel pickupEdgeIds={["E20"]} routePlan={{
    original_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N03", "N04", "N05", "N06"], edge_ids: ["E01", "E02", "E03", "E04", "E05"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "1.00", visited_node_count: 6, scoring_formula: null },
    recommended_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"], edge_ids: ["E01", "E06", "E07", "E08", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0.30", visited_node_count: 8, scoring_formula: "ROUTE_SCORE_V1" },
    candidate_routes: [{ route_id: "RTE-A1", route_name: "北环绕行线", objective: "FASTEST", node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"], edge_ids: ["E01", "E06", "E07", "E08", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_level: "LOW", risk_cost: "0.30", visited_node_count: 8, available: true, reason: null, score: "92.00", score_components: null, scoring_formula: "ROUTE_SCORE_V1", algorithm_version: "DIJKSTRA_V1", road_network_version: 7 }],
    blocked_edge_ids: ["E04"], distance_delta_km: "3.20", eta_delta_minutes: 4, visited_node_count: 8, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 7,
    network_nodes: [
      { node_id: "N01", name: "中心仓", x_km: "0.00", y_km: "0.00", node_type: "DEPOT" },
      { node_id: "N02", name: "北门", x_km: "2.00", y_km: "0.00", node_type: "JUNCTION" },
      { node_id: "N03", name: "西桥", x_km: "4.00", y_km: "0.00", node_type: "JUNCTION" },
      { node_id: "N04", name: "东河桥", x_km: "6.00", y_km: "0.00", node_type: "JUNCTION" },
      { node_id: "N05", name: "东门", x_km: "8.00", y_km: "0.00", node_type: "JUNCTION" },
      { node_id: "N06", name: "城东站", x_km: "10.00", y_km: "0.00", node_type: "STATION" },
      { node_id: "N07", name: "北环一口", x_km: "3.00", y_km: "3.00", node_type: "JUNCTION" },
      { node_id: "N08", name: "北环二口", x_km: "5.00", y_km: "4.00", node_type: "JUNCTION" },
      { node_id: "N09", name: "北环三口", x_km: "8.00", y_km: "3.00", node_type: "JUNCTION" },
    ],
    network_edges: [edge("E01", "N01", "N02"), edge("E02", "N02", "N03"), edge("E03", "N03", "N04"), edge("E04", "N04", "N05", "BLOCKED"), edge("E05", "N05", "N06"), edge("E06", "N02", "N07"), edge("E07", "N07", "N08"), edge("E08", "N08", "N09"), edge("E09", "N09", "N06")],
  }}/>); });

  expect(container.textContent).toContain("Dijkstra");
  expect(container.textContent).toContain("网络版本 7");
  expect(container.textContent).toContain("堵塞边 E04");
  expect(container.textContent).toContain("访问节点 8 个");
  expect(container.textContent).toContain("E01 → E02 → E03 → E04 → E05");
  expect(container.textContent).toContain("E01 → E06 → E07 → E08 → E09");
  expect(container.textContent).toContain("北环绕行线");
  expect(container.textContent).toContain("10.00 公里 · 20 分钟");
  expect(container.textContent).toContain("13.20 公里 · 24 分钟");
  expect(container.textContent).toContain("+3.20 公里");
  expect(container.textContent).toContain("+4 分钟");
  expect(container.querySelector('[data-edge-id="E04"]')?.getAttribute("data-route-state")).toBe("blocked");
  expect(container.querySelector('[data-edge-id="E07"]')?.getAttribute("data-route-state")).toBe("recommended");
  await act(async () => { root.unmount(); });
});

it("renders the backend audit result and all returned checks", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<AuditEvidencePanel events={[event("AUDIT_COMPLETED", { audit_result: { audit_status: "APPROVED", passed: true, reason: "All evidence persisted", checks: { route_consistency: true, memory_consistency: true, fallback_consistency: true, dispatch_execution: true }, dispatch_id: 31, requires_manual_review: true, audit_record_id: 42 } })]}/>); });

  expect(container.textContent).toContain("已批准");
  expect(container.textContent).toContain("路线一致性 · 通过");
  expect(container.textContent).toContain("记忆一致性 · 通过");
  expect(container.textContent).toContain("审核记录 42");
  expect(container.textContent).toContain("需要人工复核：是");
});
