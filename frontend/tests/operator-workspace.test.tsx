import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({ getRuntimeThreads: vi.fn() }));
const observabilityApi = vi.hoisted(() => ({ getSummary: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));
vi.mock("../src/services/api/observability-client", () => ({
  ObservabilityApiError: class ObservabilityApiError extends Error {},
  createObservabilityClient: () => observabilityApi,
}));

import { OperationsPage, OperationsWorkspace } from "../src/pages/operations-page";
import type { ObservabilitySummary } from "../src/types/observability";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const live: ObservabilitySummary = {
  state: "LIVE",
  window: "5m",
  timestamp: "2026-08-29T00:00:00Z",
  metrics: { http_qps: 12.5, http_p95: 0.12, http_error_rate: 0.001, worker_pending: 0, worker_lag: 1, dependency_up: 4 },
  series: { dependency_up: { mysql: 1, redis: 1, qdrant: 1, neo4j: 1 } },
  grafana_url: "http://localhost:3000",
};

async function renderOperator() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><OperationsWorkspace state="LIVE" data={live} /></MemoryRouter>); });
  return { container, root };
}

async function renderOperationsPage() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><OperationsPage /></MemoryRouter>); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { container, root };
}

afterEach(() => {
  workspaceReadApi.getRuntimeThreads.mockReset();
  observabilityApi.getSummary.mockReset();
  document.body.replaceChildren();
});

describe("Operator workspace", () => {
  it("test_operator_monitoring_default", async () => {
    const view = await renderOperator();
    expect(view.container.querySelector("h1")?.textContent).toBe("运行中心");
    expect(view.container.textContent).toContain("系统健康");
    expect(view.container.textContent).toContain("Worker 待处理");
    expect(view.container.textContent).toContain("API P95");
  });

  it("test_operator_no_dispatch_write", async () => {
    const view = await renderOperator();
    expect(view.container.textContent).not.toMatch(/发起智能调度|确认复核|拒绝调度/);
  });

  it("test_operator_no_override_action", async () => {
    const view = await renderOperator();
    expect(view.container.textContent).not.toMatch(/强干预|确认干预|BROKEN|UNAVAILABLE|MAINTENANCE/);
  });

  it("renders a bounded live runtime summary without changing observability metrics", async () => {
    observabilityApi.getSummary.mockResolvedValue(live);
    workspaceReadApi.getRuntimeThreads.mockResolvedValue({
      items: [{ row_id: 1, thread_id: "cf:dispatch:TASK-9", task_id: "TASK-9", status: "OVERRIDING", current_node: "routing", next_node: "dispatch", state_version: 3, checkpoint_count: 2, worker_consumer: "worker-1", terminal_at: null, updated_at: "2026-08-29T00:05:00Z" }],
      total: 8,
      next_cursor: "runtime-next",
      provenance: "LIVE",
    });

    const view = await renderOperationsPage();

    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenCalledWith({ limit: 5 }, expect.any(AbortSignal));
    expect(view.container.textContent).toContain("cf:dispatch:TASK-9");
    expect(view.container.textContent).toContain("干预中");
    expect(view.container.textContent).toContain("运行线程8");
    expect(view.container.textContent).toContain("Worker 待处理0");
    expect(view.container.textContent).toContain("智能体 P95238 ms");
    expect(view.container.textContent).toContain("混合数据");
    expect(view.container.querySelector('a[href="/runtime"]')).not.toBeNull();
    expect(view.container.textContent).not.toContain("全局运行线程列表接口尚未开放");
  });

  it("renders an explicit empty runtime summary without affecting observability", async () => {
    observabilityApi.getSummary.mockResolvedValue(live);
    workspaceReadApi.getRuntimeThreads.mockResolvedValue({ items: [], total: 0, next_cursor: null, provenance: "LIVE" });

    const view = await renderOperationsPage();

    expect(view.container.textContent).toContain("当前没有运行线程");
    expect(view.container.textContent).toContain("Worker 待处理0");
    expect(view.container.textContent).not.toContain("全局运行线程列表接口尚未开放");
  });
});
