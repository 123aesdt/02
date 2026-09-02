import { describe, expect, it, vi } from "vitest";

import { createWorkspaceReadClient } from "../src/services/api/workspace-read-client";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const overview = { orders: 12, anomalies: 3, reviews: 2, runtime_threads: 4, provenance: "LIVE" as const };
const orderPage = {
  items: [{ row_id: 7, order_no: "ORD-7", status: "PENDING", driver_id: "DR-1", vehicle_id: "VH-1", route_id: "RT-1", origin: "青县", destination: "沧州", created_at: "2026-08-29T00:00:00Z" }],
  total: 1, next_cursor: "order:7", provenance: "LIVE" as const,
};
const anomalyPage = {
  items: [{ row_id: 8, anomaly_no: "ANM-8", order_no: "ORD-7", anomaly_type: "DELAY", risk: "HIGH", description: "延迟", status: "OPEN", reported_at: "2026-08-29T00:01:00Z" }],
  total: 1, next_cursor: "anomaly:8", provenance: "MIXED" as const,
};
const reviewPage = {
  items: [{ row_id: 9, task_id: "TASK-9", order_no: "ORD-7", risk: "HIGH", reason: "人工复核", vehicle_id: "VH-1", original_route_id: "RT-1", suggested_route_id: "RT-2", status: "PENDING", created_at: "2026-08-29T00:02:00Z" }],
  total: 1, next_cursor: null, provenance: "DEMO" as const,
};
const myTaskPage = {
  items: [{ row_id: 12, task_id: "TASK-12", order_no: "ORD-12", risk: "HIGH", description: "山区道路拥堵", vehicle_id: "VH-12", original_route_id: "RT-12", suggested_route_id: "RT-13", status: "APPROVED", created_at: "2026-08-29T00:02:00Z", updated_at: "2026-08-29T00:03:00Z" }],
  summary: { total: 6, ready: 3, waiting: 1, active: 1, ended: 1 },
  total: 3, next_cursor: "12", provenance: "DEMO" as const,
};
const runtimePage = {
  items: [{ row_id: 10, thread_id: "thread-10", task_id: "TASK-9", status: "RUNNING", current_node: "routing", next_node: "audit", state_version: 2, checkpoint_count: 3, worker_consumer: "worker-1", terminal_at: null, updated_at: "2026-08-29T00:03:00Z" }],
  total: 1, next_cursor: "thread:10", provenance: "LIVE" as const,
};
const memoryPage = {
  items: [{ memory_id: "memory-11", driver_id: "DR-1", route_id: "RT-1", anomaly_type: "DELAY", historical_resolution: "改线", created_at: "2026-08-29T00:04:00Z", projection_status: "READY" }],
  total: 1, next_cursor: "opaque:memory:11", vector_dimension: 1536, provenance: "LIVE" as const,
};

describe("workspace read client", () => {
  it("requests the overview through the API boundary", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(overview));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getOverview()).resolves.toEqual(overview);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/workspace/overview", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests orders with only non-empty filters and preserves the cursor", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(orderPage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getOrders({ limit: 20, cursor: "order:6/7", query: "李师傅", status: "" })).resolves.toEqual(orderPage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/orders?limit=20&cursor=order%3A6%2F7&query=%E6%9D%8E%E5%B8%88%E5%82%85", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests the bounded anomaly list without using Mock data", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(anomalyPage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getAnomalies({ limit: 20, risk: "HIGH" })).resolves.toEqual(anomalyPage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/anomalies?limit=20&risk=HIGH", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests reviews through the real read contract", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(reviewPage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getReviews({ limit: 20 })).resolves.toEqual(reviewPage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/reviews?limit=20", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests only the current employee's tasks with state filtering", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(myTaskPage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getMyTasks({ limit: 5, cursor: "9", state: "READY" })).resolves.toEqual(myTaskPage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/my/tasks?limit=5&cursor=9&state=READY", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests runtime threads with status filtering", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(runtimePage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getRuntimeThreads({ limit: 20, status: "RUNNING" })).resolves.toEqual(runtimePage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/runtime/threads?limit=20&status=RUNNING", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("requests vector memories and leaves opaque cursor values untouched", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(memoryPage));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    await expect(client.getVectorMemories({ limit: 20, cursor: "opaque:memory:11" })).resolves.toEqual(memoryPage);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/memory/records?limit=20&cursor=opaque%3Amemory%3A11", expect.objectContaining({ credentials: "same-origin" }));
  });
});
