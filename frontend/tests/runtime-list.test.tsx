import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({ getRuntimeThreads: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt", runtimeThreadStateEnabled: true },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));

import { AuthContext, type AuthContextValue } from "../src/auth/auth-state";
import { router } from "../src/app/router";
import { ApiError } from "../src/services/api/client";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const auth: AuthContextValue = {
  status: "authenticated",
  principal: { subject_id: "operator-1", display_name: "运维一号", roles: ["OPERATOR"], permissions: ["runtime:read"], auth_method: "development_jwt", issued_at: "2026-08-29T00:00:00Z", expires_at: "2026-08-29T01:00:00Z" },
  permissions: ["runtime:read"],
  error: null,
  demoEmployees: [],
  demoEmployeesLoading: false,
  logout: vi.fn(async () => undefined),
  switchDemoEmployee: vi.fn(async () => undefined),
};

const firstPage = {
  items: [{
    row_id: 1,
    thread_id: "cf:dispatch:TASK-1",
    task_id: "TASK-1",
    status: "OVERRIDING",
    current_node: "routing",
    next_node: "dispatch",
    state_version: 7,
    checkpoint_count: 3,
    worker_consumer: "worker-1",
    terminal_at: null,
    updated_at: "2026-08-29T00:02:00Z",
    checkpoint_payload: "SENSITIVE-CHECKPOINT-STATE",
  }],
  total: 2,
  next_cursor: "runtime-next",
  provenance: "LIVE",
};

function runtimeRoute(): React.ReactNode {
  const route = router.routes[0]?.children?.find((candidate) => candidate.path === "runtime");
  if (!route?.element) throw new Error("runtime route is missing");
  return route.element;
}

async function renderRuntime() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<AuthContext.Provider value={auth}><MemoryRouter>{runtimeRoute()}</MemoryRouter></AuthContext.Provider>); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { container, root };
}

async function click(button: HTMLButtonElement) {
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

afterEach(() => {
  workspaceReadApi.getRuntimeThreads.mockReset();
  document.body.replaceChildren();
});

describe("runtime list", () => {
  it("renders approved runtime metadata and never renders checkpoint state", async () => {
    workspaceReadApi.getRuntimeThreads.mockResolvedValue(firstPage);
    const view = await renderRuntime();

    expect(view.container.textContent).toContain("cf:dispatch:TASK-1");
    expect(view.container.textContent).toContain("TASK-1");
    expect(view.container.textContent).toContain("干预中");
    expect(view.container.textContent).toContain("路径规划");
    expect(view.container.textContent).toContain("调度");
    expect(view.container.textContent).toContain("V7");
    expect(view.container.textContent).toContain("3");
    expect(view.container.textContent).toContain("worker-1");
    expect(view.container.textContent).toContain("2026-08-29T00:02:00Z");
    expect(view.container.textContent).toContain("检查点数量");
    expect(view.container.textContent).toContain("工作进程消费者");
    expect(view.container.textContent).not.toContain("checkpoint_payload");
    expect(view.container.textContent).not.toContain("SENSITIVE-CHECKPOINT-STATE");
    expect(view.container.textContent).not.toMatch(/全局强干预|确认干预/);
    expect(Array.from(view.container.querySelectorAll("a")).map((link) => link.getAttribute("href"))).toEqual(["/dispatch/TASK-1"]);
  });

  it("requests only authoritative runtime status filters", async () => {
    workspaceReadApi.getRuntimeThreads.mockResolvedValue(firstPage);
    const view = await renderRuntime();
    const filter = view.container.querySelector<HTMLSelectElement>("select");
    expect(filter).not.toBeNull();
    expect(Array.from(filter!.options).map((option) => option.value)).toEqual(["", "RUNNING", "STABLE", "OVERRIDING", "TERMINAL"]);

    await act(async () => {
      filter!.value = "OVERRIDING";
      filter!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenLastCalledWith({ limit: 20, status: "OVERRIDING" }, expect.any(AbortSignal));
  });

  it("can return from an empty next page without becoming trapped", async () => {
    workspaceReadApi.getRuntimeThreads
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce({ items: [], total: 2, next_cursor: null, provenance: "LIVE" })
      .mockResolvedValueOnce(firstPage);
    const view = await renderRuntime();

    const next = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    expect(next).not.toBeUndefined();
    await click(next!);
    expect(view.container.textContent).toContain("当前筛选页没有运行线程");

    const previous = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "上一页");
    expect(previous).not.toBeUndefined();
    await click(previous!);
    expect(view.container.textContent).toContain("cf:dispatch:TASK-1");
    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenNthCalledWith(2, { cursor: "runtime-next", limit: 20 }, expect.any(AbortSignal));
    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenNthCalledWith(3, { limit: 20 }, expect.any(AbortSignal));
  });

  it.each([
    [new ApiError(403, "FORBIDDEN", "denied"), "没有查看运行线程的权限"],
    [new ApiError(503, "RUNTIME_UNAVAILABLE", "down"), "运行线程服务暂不可用"],
    [new Error("network"), "运行线程加载失败"],
  ])("renders a recoverable read error and retries", async (error, title) => {
    workspaceReadApi.getRuntimeThreads.mockRejectedValueOnce(error).mockResolvedValueOnce(firstPage);
    const view = await renderRuntime();
    expect(view.container.textContent).toContain(title);

    const retry = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "重试");
    expect(retry).not.toBeUndefined();
    await click(retry!);

    expect(view.container.textContent).toContain("cf:dispatch:TASK-1");
    expect(workspaceReadApi.getRuntimeThreads).toHaveBeenCalledTimes(2);
  });
});
