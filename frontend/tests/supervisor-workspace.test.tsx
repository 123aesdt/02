import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({
  getReviews: vi.fn(),
  getRuntimeThreads: vi.fn(),
}));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));

import { RuntimeInterventionPanel } from "../src/components/runtime-intervention-panel";
import { SupervisorWorkspacePage } from "../src/pages/supervisor-workspace-page";
import { ApiError } from "../src/services/api/client";
import type { ReturnTypeUseRuntimeOverride } from "../src/types/runtime-workbench";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function render(element: React.ReactNode) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  return { container, root };
}

function eligibleOverride(): ReturnTypeUseRuntimeOverride {
  return {
    loading: false,
    unavailable: false,
    context: {
      thread_id: "cf:dispatch:TASK-1",
      task_id: "TASK-1",
      runtime_status: "STABLE",
      state_version: 7,
      current_node: "environment",
      next_node: "capacity",
      canonical_checkpoint_id: "checkpoint-7",
      checkpoint_available: true,
      eligibility: "ELIGIBLE",
      eligibility_reason_code: null,
      can_override: true,
      target: { entity_type: "Vehicle", entity_id: "vehicle-001", display_name: "冷链车A", field: "status", current_value: "NORMAL", allowed_new_values: ["BROKEN", "UNAVAILABLE", "MAINTENANCE"] },
      observed_at: "2026-08-29T00:00:00Z",
    },
    snapshot: null,
    reason: "",
    stale: false,
    submission: "IDLE",
    message: null,
    result: null,
    setReason: vi.fn(),
    open: vi.fn(),
    close: vi.fn(),
    submit: vi.fn(),
    refresh: vi.fn(),
  } as unknown as ReturnTypeUseRuntimeOverride;
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

function prepareLiveReads() {
  workspaceReadApi.getReviews.mockResolvedValue({
    items: [
      { row_id: 1, task_id: "TASK-review-1", order_no: "ORD-1", risk: "HIGH", reason: "路线风险", vehicle_id: "VH-1", original_route_id: "RT-1", suggested_route_id: "RT-2", status: "REVIEW_REQUIRED", created_at: "2026-08-29T00:00:00Z" },
      { row_id: 2, task_id: "TASK-review-2", order_no: "ORD-2", risk: "MEDIUM", reason: "运力需确认", vehicle_id: "VH-2", original_route_id: "RT-3", suggested_route_id: "RT-4", status: "REVIEW_REQUIRED", created_at: "2026-08-29T00:01:00Z" },
    ],
    total: 2,
    next_cursor: null,
    provenance: "MIXED",
  });
  workspaceReadApi.getRuntimeThreads.mockResolvedValue({
    items: [
      { row_id: 1, thread_id: "cf:dispatch:TASK-1", task_id: "TASK-1", status: "RUNNING", current_node: "routing", next_node: "dispatch", state_version: 7, checkpoint_count: 3, worker_consumer: "worker-1", terminal_at: null, updated_at: "2026-08-29T00:02:00Z" },
      { row_id: 2, thread_id: "cf:dispatch:TASK-2", task_id: "TASK-2", status: "STABLE", current_node: "audit", next_node: null, state_version: 4, checkpoint_count: 2, worker_consumer: "worker-2", terminal_at: null, updated_at: "2026-08-29T00:03:00Z" },
      { row_id: 3, thread_id: "cf:dispatch:TASK-3", task_id: "TASK-3", status: "OVERRIDING", current_node: "audit", next_node: null, state_version: 5, checkpoint_count: 2, worker_consumer: "worker-3", terminal_at: null, updated_at: "2026-08-29T00:04:00Z" },
      { row_id: 4, thread_id: "cf:dispatch:TASK-4", task_id: "TASK-4", status: "TERMINAL", current_node: "audit", next_node: null, state_version: 6, checkpoint_count: 4, worker_consumer: "worker-4", terminal_at: "2026-08-29T00:05:00Z", updated_at: "2026-08-29T00:05:00Z" },
    ],
    total: 4,
    next_cursor: null,
    provenance: "MIXED",
  });
}

afterEach(() => {
  workspaceReadApi.getReviews.mockReset();
  workspaceReadApi.getRuntimeThreads.mockReset();
  document.body.replaceChildren();
});

describe("Supervisor workspace", () => {
  it("renders the real read-only review queue without review actions", async () => {
    prepareLiveReads();
    const view = await render(<MemoryRouter><SupervisorWorkspacePage /></MemoryRouter>);
    await flush();
    expect(view.container.querySelector("h1")?.textContent).toBe("调度主管台");
    expect(view.container.textContent).toContain("TASK-review-2");
    expect(view.container.textContent).toContain("等待人工复核");
    expect(view.container.textContent).toContain("进入复核时间");
    expect(view.container.textContent).not.toContain("等待时间");
    expect(view.container.querySelector('a[href="/dispatch/TASK-review-2"]')).not.toBeNull();
    expect(Array.from(view.container.querySelectorAll("button")).some((button) => /批准|拒绝/.test(button.textContent ?? ""))).toBe(false);
  });

  it("uses review totals and first-page runtime statuses in supervisor metrics", async () => {
    prepareLiveReads();
    const view = await render(<MemoryRouter><SupervisorWorkspacePage /></MemoryRouter>);
    await flush();
    expect(view.container.textContent).toContain("待复核2");
    expect(view.container.textContent).toContain("本页运行中1");
    expect(view.container.textContent).toContain("本页稳定1");
    expect(view.container.textContent).toContain("本页干预中1");
    expect(view.container.textContent).toContain("本页已结束1");
    expect(view.container.textContent).toContain("混合数据");
    expect(view.container.textContent).not.toContain("本页异常");
    expect(view.container.textContent).not.toContain("全局运行线程列表接口尚未开放");
  });

  it.each([
    [new ApiError(403, "FORBIDDEN", "denied"), "没有查看运行态摘要的权限"],
    [new ApiError(503, "RUNTIME_UNAVAILABLE", "down"), "运行态摘要服务暂不可用"],
  ])("renders a recoverable supervisor runtime summary state", async (error, title) => {
    prepareLiveReads();
    workspaceReadApi.getRuntimeThreads.mockRejectedValueOnce(error);
    const view = await render(<MemoryRouter><SupervisorWorkspacePage /></MemoryRouter>);
    await flush();
    expect(view.container.textContent).toContain(title);

    const retry = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "重试");
    expect(retry).not.toBeUndefined();
    await act(async () => { retry!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    await flush();
    expect(view.container.textContent).toContain("本页干预中1");
  });

  it("test_supervisor_runtime_override_visible", async () => {
    const view = await render(<RuntimeInterventionPanel override={eligibleOverride()} canOverride />);
    const action = view.container.querySelector<HTMLButtonElement>('button[data-target="BROKEN"]');
    expect(action?.textContent).toBe("故障");
    expect(action?.disabled).toBe(false);
  });

  it("test_supervisor_intervention_403_without_permission", async () => {
    const view = await render(<RuntimeInterventionPanel override={eligibleOverride()} canOverride={false} />);
    expect(view.container.textContent).toContain("无权限执行运行态强干预");
    expect([...view.container.querySelectorAll("button")].every((button) => button.disabled)).toBe(true);
  });
});
