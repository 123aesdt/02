import { describe, expect, it, vi } from "vitest";

import {
  getAnomalies,
  getMemoryRecords,
  getOrders,
} from "../src/services/workspace-service";
import { getMemoryFact } from "../src/services/api/memory-client";

describe("Workspace mock adapter", () => {
  it("filters the anomaly desk by its confirmed core dispatch", async () => {
    const records = await getAnomalies({ query: "CF-20260821-00128", risk: "HIGH" });

    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      id: "ANM-20260821-017",
      taskId: "TASK-20260821-0042",
      driver: "李师傅",
    });
  });

  it("exposes the entity-memory evidence without an ID lookup shortcut", async () => {
    const records = await getMemoryRecords({ query: "雨天 新平路" });

    expect(records[0]).toMatchObject({
      memoryId: "memory-rain-li",
      vectorDimension: 2560,
      resolution: "建议改走102国道",
    });
  });

  it("keeps the core order linked to its dispatch task", async () => {
    const records = await getOrders({ query: "00128" });

    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      orderId: "CF-20260821-00128",
      taskId: "TASK-20260821-0042",
    });
  });

  it("loads the bounded shared-memory control-plane detail", async () => {
    const request = vi.fn().mockResolvedValue({ data: { fact_key: "smf_test", version: 8 }, status: 200 });

    const result = await getMemoryFact("smf_test", { request });

    expect(request).toHaveBeenCalledWith("/api/v1/memory/facts/smf_test");
    expect(result.version).toBe(8);
  });
});
