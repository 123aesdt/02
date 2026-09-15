import { describe, expect, it, vi } from "vitest";

import { createVehicleOperationsClient } from "../src/services/api/vehicle-operations-client";


describe("vehicle operations API client", () => {
  it("loads one task-scoped map snapshot with authentication handled by the shared client", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: "TASK-1", nodes: [], edges: [], vehicles: [], routes: [], stages: [], timeline: [] }), { status: 200 }));
    const client = createVehicleOperationsClient({ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch });

    const snapshot = await client.getMapSnapshot("TASK-1");

    expect(snapshot.task_id).toBe("TASK-1");
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/map/snapshot?task_id=TASK-1", expect.objectContaining({ headers: expect.any(Headers) }));
  });

  it("loads a driver-scoped snapshot through the read-only endpoint", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_id: "TASK-1", nodes: [], edges: [], vehicles: [], routes: [], stages: [], timeline: [] }), { status: 200 }));
    const client = createVehicleOperationsClient({ baseUrl: "http://api.test", fetchImpl: fetchImpl as typeof fetch });

    await client.getDriverOperationSnapshot("TASK-1");

    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/driver/operation-snapshot?task_id=TASK-1", expect.objectContaining({ headers: expect.any(Headers) }));
  });
});
