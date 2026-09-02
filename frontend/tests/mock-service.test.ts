import { describe, expect, it } from "vitest";

import { getDashboardSnapshot, getDispatchDetail } from "../src/services/dispatch-service";

describe("Mock service adapter", () => {
  it("returns the clickable rainy-road anomaly for the dashboard", async () => {
    const dashboard = await getDashboardSnapshot();

    expect(dashboard.recentAnomalies[0]).toMatchObject({
      id: "ANM-20260821-017",
      taskId: "TASK-20260821-0042",
      type: "暴雨道路湿滑",
    });
  });

  it("returns dispatch evidence that preserves the backend-shaped task identifiers", async () => {
    const detail = await getDispatchDetail("TASK-20260821-0042");

    expect(detail).toMatchObject({
      taskId: "TASK-20260821-0042",
      memory: { memoryId: "memory-rain-li", adopted: true },
      dispatch: { targetRoute: "national-102", fallbackUsed: true },
      audit: { status: "APPROVED" },
      graphMemory: {
        used: true,
        facts: ["李师傅 → HAS_RISK_ON → 新平路", "102国道 → ALTERNATIVE_TO → 新平路"],
      },
    });
    expect(detail.agents.map((agent) => agent.id)).toEqual([
      "intake", "memory", "graph_memory", "environment", "capacity", "routing", "dispatch", "audit",
    ]);
  });
});
