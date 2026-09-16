import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";

const workspaceReadApi = vi.hoisted(() => ({
  getOverview: vi.fn(),
  getOrders: vi.fn(),
  getAnomalies: vi.fn(),
  getReviews: vi.fn(),
  getMyTasks: vi.fn(),
  getRuntimeThreads: vi.fn(),
  getVectorMemories: vi.fn(),
}));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));

import {
  useAnomaliesRead,
  useOrdersRead,
  useOverview,
  useReviewsRead,
  useMyTasksRead,
  useRuntimeThreadsRead,
  useVectorMemoriesRead,
} from "../src/hooks/use-workspace-reads";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const orderPage = {
  items: [{ row_id: 7, order_no: "ORD-7", status: "PENDING", driver_id: "DR-1", vehicle_id: "VH-1", route_id: "RT-1", origin: "青县", destination: "沧州", created_at: "2026-08-29T00:00:00Z" }],
  total: 1, next_cursor: null, provenance: "LIVE" as const,
};
const myTaskPage = {
  items: [{ row_id: 12, task_id: "TASK-12", order_no: "ORD-12", risk: "HIGH", description: "山区道路拥堵", vehicle_id: "VH-12", original_route_id: "RT-12", suggested_route_id: "RT-13", status: "APPROVED", created_at: "2026-08-29T00:02:00Z", updated_at: "2026-08-29T00:03:00Z" }],
  summary: { total: 6, ready: 3, waiting: 1, active: 1, ended: 1 },
  total: 3, next_cursor: "12", provenance: "DEMO" as const,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => { resolve = resolvePromise; reject = rejectPromise; });
  return { promise, resolve, reject };
}

async function renderHook<T>(render: () => T) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  let current!: T;
  function Probe() { current = render(); return null; }
  async function update() { await act(async () => { root.render(<Probe />); }); }
  await update();
  return { get current() { return current; }, update, unmount: async () => { await act(async () => { root.unmount(); }); } };
}

async function flush() { await act(async () => { await Promise.resolve(); }); }

afterEach(() => {
  for (const method of Object.values(workspaceReadApi)) method.mockReset();
  document.body.replaceChildren();
});

describe("workspace read hooks", () => {
  it("moves from loading to ready and keeps API provenance", async () => {
    const pending = deferred<typeof orderPage>();
    workspaceReadApi.getOrders.mockReturnValue(pending.promise);
    const result = await renderHook(() => useOrdersRead({ query: "李师傅" }));

    expect(result.current.state).toBe("LOADING");
    await act(async () => { pending.resolve(orderPage); });
    await flush();
    expect(result.current).toMatchObject({ state: "READY", data: { provenance: "LIVE" } });
    expect(workspaceReadApi.getOrders).toHaveBeenCalledWith({ query: "李师傅" }, expect.any(AbortSignal));
    await result.unmount();
  });

  it("maps an empty page to EMPTY", async () => {
    workspaceReadApi.getReviews.mockResolvedValue({ items: [], total: 0, next_cursor: null, provenance: "LIVE" });
    const result = await renderHook(() => useReviewsRead());

    await flush();
    expect(result.current.state).toBe("EMPTY");
    await result.unmount();
  });

  it("loads the signed-in employee's task queue with the selected state", async () => {
    workspaceReadApi.getMyTasks.mockResolvedValue(myTaskPage);
    const result = await renderHook(() => useMyTasksRead({ limit: 5, state: "READY" }));

    await flush();
    expect(result.current).toMatchObject({ state: "READY", data: myTaskPage });
    expect(workspaceReadApi.getMyTasks).toHaveBeenCalledWith({ limit: 5, state: "READY" }, expect.any(AbortSignal));
    await result.unmount();
  });

  it("maps 403 API errors to FORBIDDEN", async () => {
    workspaceReadApi.getOverview.mockRejectedValue(new ApiError(403, "FORBIDDEN", "not used for classification"));
    const result = await renderHook(() => useOverview());

    await flush();
    expect(result.current.state).toBe("FORBIDDEN");
    await result.unmount();
  });

  it("maps 503 API errors to UNAVAILABLE", async () => {
    workspaceReadApi.getVectorMemories.mockRejectedValue(new ApiError(503, "VECTOR_MEMORY_UNAVAILABLE", "not used for classification"));
    const result = await renderHook(() => useVectorMemoriesRead());

    await flush();
    expect(result.current.state).toBe("UNAVAILABLE");
    await result.unmount();
  });

  it("preserves vector metadata for a successful empty page", async () => {
    const emptyVectorPage = { items: [], total: 0, next_cursor: null, vector_dimension: 128, provenance: "MIXED" as const };
    workspaceReadApi.getVectorMemories.mockResolvedValue(emptyVectorPage);
    const result = await renderHook(() => useVectorMemoriesRead());

    await flush();
    expect(result.current).toMatchObject({ state: "READY", data: emptyVectorPage });
    await result.unmount();
  });

  it("maps non-status failures to ERROR", async () => {
    workspaceReadApi.getAnomalies.mockRejectedValue(new Error("network failed"));
    const result = await renderHook(() => useAnomaliesRead({ risk: "HIGH" }));

    await flush();
    expect(result.current.state).toBe("ERROR");
    await result.unmount();
  });

  it("refreshes a runtime thread read on demand", async () => {
    workspaceReadApi.getRuntimeThreads.mockResolvedValue({ items: [], total: 0, next_cursor: null, provenance: "LIVE" });
    const result = await renderHook(() => useRuntimeThreadsRead({ status: "RUNNING" }));

    await flush();
    await act(async () => { result.current.refresh(); });
    await flush();
    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenCalledTimes(2);
    await result.unmount();
  });

  it("does not cancel an in-flight read and runs one queued refresh after it completes", async () => {
    const pending = deferred<{ items: []; total: 0; next_cursor: null; provenance: "LIVE" }>();
    workspaceReadApi.getAnomalies.mockReturnValueOnce(pending.promise).mockResolvedValue({
      items: [], total: 0, next_cursor: null, provenance: "LIVE",
    });
    const result = await renderHook(() => useAnomaliesRead());

    await act(async () => {
      result.current.refresh();
      result.current.refresh();
    });
    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(1);

    await act(async () => { pending.resolve({ items: [], total: 0, next_cursor: null, provenance: "LIVE" }); });
    await flush();
    await flush();
    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(2);
    await result.unmount();
  });

  it("times out a hung read and resumes a queued refresh", async () => {
    vi.useFakeTimers();
    const hung = deferred<{ items: []; total: 0; next_cursor: null; provenance: "LIVE" }>();
    workspaceReadApi.getAnomalies.mockReturnValueOnce(hung.promise).mockResolvedValue({
      items: [], total: 0, next_cursor: null, provenance: "LIVE",
    });
    const result = await renderHook(() => useAnomaliesRead());
    await act(async () => { result.current.refresh(); });

    await act(async () => { await vi.advanceTimersByTimeAsync(4_999); });
    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    await flush();

    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(2);
    expect(result.current.state).toBe("EMPTY");
    await result.unmount();
    vi.useRealTimers();
  });

  it("does not let a stale filter request replace newer data", async () => {
    const first = deferred<typeof orderPage>();
    const second = deferred<typeof orderPage>();
    workspaceReadApi.getOrders.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    let query = "first";
    const result = await renderHook(() => useOrdersRead({ query }));

    query = "second";
    await result.update();
    await act(async () => { second.resolve({ ...orderPage, items: [{ ...orderPage.items[0], order_no: "ORD-SECOND" }] }); });
    await flush();
    await act(async () => { first.resolve({ ...orderPage, items: [{ ...orderPage.items[0], order_no: "ORD-FIRST" }] }); });
    await flush();
    expect(result.current.data?.items[0]?.order_no).toBe("ORD-SECOND");
    await result.unmount();
  });
});
