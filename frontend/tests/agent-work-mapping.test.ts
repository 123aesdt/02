import { describe, expect, it } from "vitest";

import type { TaskEvent } from "../src/types/task-events";
import { buildAgentWork, formatAgentElapsed } from "../src/utils/agent-work";

function event(node: string, data: Record<string, unknown>): TaskEvent {
  return {
    event_id: `event-${node}`,
    task_id: "TASK-DEMO",
    event_type: `${node.toUpperCase()}_COMPLETED`,
    node,
    status: "PROCESSING",
    timestamp: "2026-09-15T05:00:00.031Z",
    sequence: 1,
    data,
  };
}

describe("Agent work presentation", () => {
  it.each([
    ["intake", {
      vehicle_id: "V-002",
      affected_edge_ids: ["E04"],
      origin_node_id: "N01",
      destination_node_id: "N06",
      sandtable_context_loaded: true,
    }, "已规范化异常并锁定车辆 V-002"],
    ["entity_memory", {
      memory_results: [{ memory_id: "MEM-1", similarity_score: 0.91, route_id: "ROUTE-01" }],
    }, "召回 1 条历史处置记忆"],
    ["graph_memory", {
      graph_memory_used: true,
      graph_memory_facts: [{ relation_type: "HAS_RISK_ON" }],
      graph_memory_paths: [{ entities: ["D-003", "V-005"] }],
    }, "召回 1 条关系事实和 1 条可解释路径"],
    ["environment", {
      weather: "rain",
      road_condition: "blocked",
      environment_risk: "high",
      fallback_used: false,
    }, "识别降雨、道路阻断，环境风险 高"],
    ["capacity", {
      vehicle_id: "V-002",
      vehicle_available: true,
      vehicle_reassigned: false,
    }, "已确认车辆 V-002 具备继续执行条件"],
    ["routing", {
      recommended_route: "RTE-SAFE-01",
      blocked_edge_ids: ["E04"],
      recommended_path: { distance_km: "13.20", estimated_minutes: 24 },
    }, "已避开 E04，推荐路线 RTE-SAFE-01"],
    ["dispatch", {
      target_vehicle_id: "V-005",
      target_route_id: "RTE-SAFE-01",
      version: 2,
      executed: true,
    }, "调度已执行：V-005 将按 RTE-SAFE-01 行驶"],
    ["audit", {
      audit_result: {
        audit_status: "APPROVED",
        passed: true,
        checks: { route_connectivity: true, blocked_edge_exclusion: true },
      },
    }, "2 项校验通过，允许自动发布"],
  ])("turns %s data into a readable work result", (node, data, expected) => {
    const work = buildAgentWork(node, event(node, data));

    expect(work.result).toContain(expected);
    expect(work.result).not.toContain("{");
    expect(work.input).not.toBe("");
    expect(work.action).not.toBe("");
    expect(work.eventId).toBe(`event-${node}`);
  });

  it("uses the paired start and completion timestamps for the displayed duration", () => {
    expect(formatAgentElapsed(
      "2026-09-15T05:00:00.000Z",
      "2026-09-15T05:00:00.031Z",
    )).toBe("31 ms");
  });
});
