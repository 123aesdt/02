import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";

import { AuditEvidencePanel } from "../src/components/audit-evidence-panel";
import { RoutingEvidencePanel } from "../src/components/routing-evidence-panel";
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

it("renders the backend audit result and all returned checks", async () => {
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  await act(async () => { root.render(<AuditEvidencePanel events={[event("AUDIT_COMPLETED", { audit_result: { audit_status: "APPROVED", passed: true, reason: "All evidence persisted", checks: { route_consistency: true, memory_consistency: true, fallback_consistency: true, dispatch_execution: true }, dispatch_id: 31, requires_manual_review: true, audit_record_id: 42 } })]}/>); });

  expect(container.textContent).toContain("已批准");
  expect(container.textContent).toContain("路线一致性 · 通过");
  expect(container.textContent).toContain("记忆一致性 · 通过");
  expect(container.textContent).toContain("审核记录 42");
  expect(container.textContent).toContain("需要人工复核：是");
});
