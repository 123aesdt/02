import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";

const workspaceApi = vi.hoisted(() => ({ getMyTasks: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceApi }));
vi.mock("../src/auth/auth-state", () => ({ useHasPermission: () => true }));

import { DispatcherWorkspacePage } from "../src/pages/dispatcher-workspace-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const summary = { total: 6, ready: 3, waiting: 1, active: 1, ended: 1 };

const taskPages = {
  READY: {
    items: [{ row_id: 12, task_id: "DEMO-TASK-012", order_no: "DEMO-ORDER-012", risk: "HIGH", description: "乡道积水，需要安全绕行", vehicle_id: "demo-vehicle-012", original_route_id: "云岭乡道", suggested_route_id: "国道-108", status: "APPROVED", created_at: "2026-08-30T08:00:00Z", updated_at: "2026-08-30T08:05:00Z" }],
    summary, total: 1, next_cursor: null, provenance: "DEMO" as const,
  },
  ACTIVE: {
    items: [{ row_id: 13, task_id: "DEMO-TASK-013", order_no: "DEMO-ORDER-013", risk: "MEDIUM", description: "正在计算绕行路线", vehicle_id: "demo-vehicle-013", original_route_id: "东川环线", suggested_route_id: "省道-204", status: "RUNNING", created_at: "2026-08-30T07:00:00Z", updated_at: "2026-08-30T08:10:00Z" }],
    summary, total: 1, next_cursor: null, provenance: "DEMO" as const,
  },
  ENDED: {
    items: [{ row_id: 14, task_id: "DEMO-TASK-014", order_no: "DEMO-ORDER-014", risk: "LOW", description: "绕行方案已经完成", vehicle_id: "demo-vehicle-014", original_route_id: "新平乡道", suggested_route_id: "县道-016", status: "SUCCEEDED", created_at: "2026-08-29T07:00:00Z", updated_at: "2026-08-30T07:50:00Z" }],
    summary, total: 1, next_cursor: null, provenance: "DEMO" as const,
  },
};

async function renderDispatcher() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><DispatcherWorkspacePage /></MemoryRouter>); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  return { container, root };
}

beforeEach(() => {
  workspaceApi.getMyTasks.mockImplementation((filters: { state?: keyof typeof taskPages } = {}) =>
    Promise.resolve(taskPages[filters.state ?? "READY"]),
  );
});

afterEach(() => {
  workspaceApi.getMyTasks.mockReset();
  document.body.replaceChildren();
});

describe("Dispatcher workspace", () => {
  it("test_dispatcher_default_workspace prioritizes real work boundaries", async () => {
    const { container } = await renderDispatcher();
    expect(container.querySelector("h1")?.textContent).toBe("调度工作台");
    for (const section of ["工作概览", "待执行任务", "调度执行中", "AI 建议", "最近完成"]) {
      expect(container.textContent).toContain(section);
    }
    expect([...container.querySelectorAll("a")].some((link) => link.textContent === "发起智能调度")).toBe(true);
  });

  it("test_dispatcher_no_runtime_override", async () => {
    const { container } = await renderDispatcher();
    expect(container.textContent).not.toMatch(/强干预|Runtime Override|修改检查点/);
  });

  it("projects ready, active, and ended employee tasks into their matching sections", async () => {
    const { container } = await renderDispatcher();
    expect(container.textContent).toContain("全部任务");
    expect(container.textContent).toContain("DEMO-TASK-012");
    expect(container.textContent).toContain("DEMO-TASK-013");
    expect(container.textContent).toContain("DEMO-TASK-014");
    expect(container.textContent).toContain("已批准");
    expect(container.textContent).toContain("运行中");
    expect(container.textContent).toContain("已完成");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/dispatch/DEMO-TASK-012"]')).not.toBeNull();
    expect(container.querySelector<HTMLAnchorElement>('a[href="/dispatch/DEMO-TASK-013"]')).not.toBeNull();
    expect(container.querySelector<HTMLAnchorElement>('a[href="/dispatch/DEMO-TASK-014"]')).not.toBeNull();
    expect(container.textContent).not.toContain("调度任务列表接口尚未开放");
    expect(container.textContent).not.toContain("最近完成任务接口尚未开放");
    expect(workspaceApi.getMyTasks).toHaveBeenCalledWith({ limit: 5, state: "READY" }, expect.any(AbortSignal));
    expect(workspaceApi.getMyTasks).toHaveBeenCalledWith({ limit: 5, state: "ACTIVE" }, expect.any(AbortSignal));
    expect(workspaceApi.getMyTasks).toHaveBeenCalledWith({ limit: 5, state: "ENDED" }, expect.any(AbortSignal));
  });

  it("keeps a task service outage explicit instead of showing a fake empty queue", async () => {
    workspaceApi.getMyTasks.mockRejectedValue(new ApiError(503, "MY_TASKS_UNAVAILABLE", "down"));
    const { container } = await renderDispatcher();
    expect(container.textContent).toContain("我的任务服务暂不可用");
    expect(container.textContent).not.toContain("当前没有待处理任务");
  });
});
