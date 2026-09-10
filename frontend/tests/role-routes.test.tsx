import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({
  getReviews: vi.fn(),
  getAnomalies: vi.fn(),
  getMyTasks: vi.fn(),
  getRuntimeThreads: vi.fn(),
}));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://api.test",
    authenticationMode: "development_jwt",
    runtimeThreadStateEnabled: true,
  },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));

import { AuthContext, type AuthContextValue } from "../src/auth/auth-state";
import { PermissionGate } from "../src/auth/permission-gate";
import { RoleLandingRedirect, router } from "../src/app/router";
import { ApiError } from "../src/services/api/client";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const principal = {
  subject_id: "dispatcher-1",
  display_name: "调度员一号",
  roles: ["DISPATCHER"],
  permissions: ["dispatch:read", "dispatch:create"],
  auth_method: "development_jwt" as const,
  issued_at: "2026-08-29T00:00:00Z",
  expires_at: "2026-08-29T01:00:00Z",
};

const reviewPage = {
  items: [{ row_id: 2, task_id: "TASK-review-2", order_no: "ORD-2", risk: "HIGH", reason: "路线需人工确认", vehicle_id: "VH-2", original_route_id: "RT-1", suggested_route_id: "RT-2", status: "REVIEW_REQUIRED", created_at: "2026-08-29T00:01:00Z" }],
  total: 2,
  next_cursor: "review-next",
  provenance: "LIVE" as const,
};

const myTaskPage = {
  items: [{ row_id: 12, task_id: "TASK-12", order_no: "ORD-12", risk: "HIGH", description: "乡道积水", vehicle_id: "VH-12", original_route_id: "RT-12", suggested_route_id: "RT-13", status: "APPROVED", created_at: "2026-08-29T00:02:00Z", updated_at: "2026-08-29T00:03:00Z" }],
  summary: { total: 1, ready: 1, waiting: 0, active: 0, ended: 0 },
  total: 1, next_cursor: null, provenance: "LIVE" as const,
};

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  await act(async () => { await Promise.resolve(); });
  return { root, container };
}

async function click(button: HTMLButtonElement) {
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

function auth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: "authenticated",
    principal,
    permissions: principal.permissions,
    error: null,
    demoEmployees: [],
    demoEmployeesLoading: false,
    logout: vi.fn(async () => undefined),
    switchDemoEmployee: vi.fn(async () => undefined),
    ...overrides,
  };
}

function routeElement(path: string): React.ReactNode {
  const route = router.routes[0]?.children?.find((candidate) => candidate.path === path);
  if (!route?.element) throw new Error(`route ${path} is missing`);
  return route.element;
}

function authorizedFor(permission: string): AuthContextValue {
  return auth({ permissions: [permission], principal: { ...principal, permissions: [permission] } });
}

afterEach(() => {
  workspaceReadApi.getReviews.mockReset();
  workspaceReadApi.getAnomalies.mockReset();
  workspaceReadApi.getMyTasks.mockReset();
  workspaceReadApi.getRuntimeThreads.mockReset();
  document.body.replaceChildren();
});

describe("role routes", () => {
  it("test_dispatcher_default_workspace", async () => {
    const view = await render(
      <AuthContext.Provider value={auth()}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route index element={<RoleLandingRedirect />} />
            <Route path="workspace" element={<h1>调度工作台</h1>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(view.container.querySelector("h1")?.textContent).toBe("调度工作台");
  });

  it("test_unauthorized_route", async () => {
    const view = await render(<PermissionGate mode="api" status="authenticated" permissions={["dispatch:read"]} required="monitor:read"><h1>运行中心</h1></PermissionGate>);
    expect(view.container.querySelector("h2")?.textContent).toBe("无权访问");
    expect(view.container.textContent).not.toContain("运行中心");
  });

  it("test_session_expired", async () => {
    const view = await render(<PermissionGate mode="api" status="expired" permissions={[]} required="monitor:read"><h1>运行中心</h1></PermissionGate>);
    expect(view.container.querySelector("h2")?.textContent).toBe("会话已过期");
    expect(view.container.textContent).not.toContain("无权访问");
  });

  it("exposes the vehicle situation map as a protected administrator workspace", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue({ items: [], total: 0, next_cursor: null, provenance: "LIVE" });
    const allowed = await render(<AuthContext.Provider value={authorizedFor("dispatch:review")}><MemoryRouter>{routeElement("fleet-live-map")}</MemoryRouter></AuthContext.Provider>);
    expect(allowed.container.textContent).toContain("车辆态势地图");

    const denied = await render(<AuthContext.Provider value={authorizedFor("dispatch:read")}><MemoryRouter>{routeElement("fleet-live-map")}</MemoryRouter></AuthContext.Provider>);
    expect(denied.container.querySelector("h2")?.textContent).toBe("无权访问");
  });

  it("replaces the reviews placeholder while preserving its role guard", async () => {
    workspaceReadApi.getReviews.mockResolvedValue(reviewPage);
    const allowed = await render(<AuthContext.Provider value={authorizedFor("dispatch:review")}><MemoryRouter>{routeElement("reviews")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(allowed.container.textContent).toContain("TASK-review-2");
    expect(allowed.container.textContent).toContain("实时数据");
    expect(allowed.container.textContent).toContain("进入复核时间");
    expect(allowed.container.textContent).not.toContain("等待时间");
    expect(allowed.container.textContent).toContain("2026-08-29T00:01:00Z");
    expect(Array.from(allowed.container.querySelectorAll("button")).some((button) => button.textContent === "批准")).toBe(true);
    expect(Array.from(allowed.container.querySelectorAll("button")).some((button) => button.textContent === "拒绝")).toBe(true);
    expect(allowed.container.textContent).not.toContain("复核队列接口尚未开放");

    workspaceReadApi.getReviews.mockClear();
    const denied = await render(<AuthContext.Provider value={authorizedFor("dispatch:read")}><MemoryRouter>{routeElement("reviews")}</MemoryRouter></AuthContext.Provider>);
    expect(denied.container.querySelector("h2")?.textContent).toBe("无权访问");
    expect(workspaceReadApi.getReviews).not.toHaveBeenCalled();
  });

  it("replaces the my-tasks placeholder while preserving employee permissions", async () => {
    workspaceReadApi.getMyTasks.mockResolvedValue(myTaskPage);
    const allowed = await render(<AuthContext.Provider value={authorizedFor("dispatch:read")}><MemoryRouter>{routeElement("my-tasks")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(allowed.container.textContent).toContain("TASK-12");
    expect(allowed.container.textContent).toContain("实时数据");
    expect(allowed.container.textContent).not.toContain("我的任务数据接口尚未开放");

    workspaceReadApi.getMyTasks.mockClear();
    const denied = await render(<AuthContext.Provider value={authorizedFor("orders:read")}><MemoryRouter>{routeElement("my-tasks")}</MemoryRouter></AuthContext.Provider>);
    expect(denied.container.querySelector("h2")?.textContent).toBe("无权访问");
    expect(workspaceReadApi.getMyTasks).not.toHaveBeenCalled();
  });

  it("routes dispatch staff to the anomaly-created task center", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [{ row_id: 1, anomaly_no: "ANOM-1", order_no: "ORD-1", driver_id: "driver-1", vehicle_id: "vehicle-1", route_id: "route-1", latest_task_id: "TASK-1", anomaly_type: "ROAD_HAZARD", risk: "HIGH", description: "道路风险", status: "REPORTED", reported_at: "2026-09-01T08:00:00Z" }],
      total: 1,
      next_cursor: null,
      provenance: "LIVE",
    });
    const view = await render(<AuthContext.Provider value={authorizedFor("dispatch:create")}><MemoryRouter>{routeElement("dispatch")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(view.container.textContent).toContain("异常调度任务");
    expect(view.container.textContent).not.toContain("发起一项新的调度任务");
  });

  it("guards the driver report route with the dedicated permission", async () => {
    workspaceReadApi.getMyTasks.mockResolvedValue(myTaskPage);
    const allowed = await render(<AuthContext.Provider value={authorizedFor("anomalies:report")}><MemoryRouter initialEntries={["/report-issue?taskId=TASK-12"]}>{routeElement("report-issue")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(allowed.container.textContent).toContain("提出配送问题");

    const denied = await render(<AuthContext.Provider value={authorizedFor("dispatch:read")}><MemoryRouter>{routeElement("report-issue")}</MemoryRouter></AuthContext.Provider>);
    expect(denied.container.querySelector("h2")?.textContent).toBe("无权访问");
  });

  it("returns from an empty review page and keeps API provenance", async () => {
    workspaceReadApi.getReviews
      .mockResolvedValueOnce(reviewPage)
      .mockResolvedValueOnce({ items: [], total: 2, next_cursor: null, provenance: "LIVE" })
      .mockResolvedValueOnce(reviewPage);
    const view = await render(<AuthContext.Provider value={authorizedFor("dispatch:review")}><MemoryRouter>{routeElement("reviews")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(view.container.textContent).toContain("实时数据");

    const next = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    expect(next).not.toBeUndefined();
    await click(next!);
    expect(view.container.textContent).toContain("当前分页没有等待人工复核任务");

    const previous = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "上一页");
    expect(previous).not.toBeUndefined();
    await click(previous!);
    expect(view.container.textContent).toContain("TASK-review-2");
    expect(workspaceReadApi.getReviews).toHaveBeenNthCalledWith(2, { cursor: "review-next", limit: 20 }, expect.any(AbortSignal));
    expect(workspaceReadApi.getReviews).toHaveBeenNthCalledWith(3, { limit: 20 }, expect.any(AbortSignal));
  });

  it.each([
    [new ApiError(403, "FORBIDDEN", "denied"), "没有查看人工复核队列的权限"],
    [new ApiError(503, "REVIEWS_UNAVAILABLE", "down"), "人工复核队列服务暂不可用"],
    [new Error("network"), "人工复核队列加载失败"],
  ])("renders a recoverable review error and retries", async (error, title) => {
    workspaceReadApi.getReviews.mockRejectedValueOnce(error).mockResolvedValueOnce(reviewPage);
    const view = await render(<AuthContext.Provider value={authorizedFor("dispatch:review")}><MemoryRouter>{routeElement("reviews")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(view.container.textContent).toContain(title);

    const retry = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "重试");
    expect(retry).not.toBeUndefined();
    await click(retry!);
    expect(view.container.textContent).toContain("TASK-review-2");
    expect(workspaceReadApi.getReviews).toHaveBeenCalledTimes(2);
  });

  it("replaces the runtime placeholder while preserving its role guard", async () => {
    workspaceReadApi.getRuntimeThreads.mockResolvedValue({
      items: [{ row_id: 1, thread_id: "cf:dispatch:TASK-1", task_id: "TASK-1", status: "RUNNING", current_node: "routing", next_node: "dispatch", state_version: 7, checkpoint_count: 3, worker_consumer: "worker-1", terminal_at: null, updated_at: "2026-08-29T00:02:00Z" }],
      total: 1,
      next_cursor: null,
      provenance: "LIVE",
    });
    const allowed = await render(<AuthContext.Provider value={authorizedFor("runtime:read")}><MemoryRouter>{routeElement("runtime")}</MemoryRouter></AuthContext.Provider>);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(allowed.container.textContent).toContain("cf:dispatch:TASK-1");
    expect(allowed.container.textContent).not.toContain("全局运行态列表接口尚未开放");

    workspaceReadApi.getRuntimeThreads.mockClear();
    const denied = await render(<AuthContext.Provider value={authorizedFor("dispatch:read")}><MemoryRouter>{routeElement("runtime")}</MemoryRouter></AuthContext.Provider>);
    expect(denied.container.querySelector("h2")?.textContent).toBe("无权访问");
    expect(workspaceReadApi.getRuntimeThreads).not.toHaveBeenCalled();
  });
});
