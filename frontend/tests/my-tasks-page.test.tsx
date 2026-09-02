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

import { MyTasksPage } from "../src/pages/my-tasks-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const myTaskPage = {
  items: [{
    row_id: 12,
    task_id: "DEMO-TASK-012",
    order_no: "DEMO-ORDER-012",
    risk: "HIGH",
    description: "乡道积水，需要安全绕行",
    vehicle_id: "demo-vehicle-012",
    original_route_id: "云岭乡道",
    suggested_route_id: "国道-108",
    status: "APPROVED",
    created_at: "2026-08-30T08:00:00Z",
    updated_at: "2026-08-30T08:05:00Z",
    origin: "青云镇",
    destination: "临港镇",
    publication_status: "PUBLISHED",
    published_at: "2026-08-30T08:06:00Z",
    route_instruction: "从青云镇出发，按国道-108行驶，前往临港镇。途中注意现场路况并服从安全调度。",
  }, {
    row_id: 13,
    task_id: "DEMO-TASK-ENDED",
    order_no: "DEMO-ORDER-ENDED",
    risk: "LOW",
    description: "已完成配送",
    vehicle_id: "demo-vehicle-013",
    original_route_id: "云岭乡道",
    suggested_route_id: "国道-108",
    status: "COMPLETED",
    created_at: "2026-08-30T07:00:00Z",
    updated_at: "2026-08-30T09:00:00Z",
    origin: "青云镇",
    destination: "临港镇",
    publication_status: "PUBLISHED",
    published_at: "2026-08-30T09:00:00Z",
    route_instruction: "任务已完成。",
  }],
  summary: { total: 6, ready: 3, waiting: 1, active: 1, ended: 1 },
  total: 2,
  next_cursor: null,
  provenance: "DEMO" as const,
};

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

async function renderPage() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><MyTasksPage /></MemoryRouter>); });
  await flush();
  return { container, root };
}

async function click(container: HTMLElement, text: string) {
  const button = [...container.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.trim() === text);
  if (!button) throw new Error(`Missing button: ${text}`);
  await act(async () => { button.click(); });
  await flush();
}

beforeEach(() => {
  workspaceApi.getMyTasks.mockResolvedValue(myTaskPage);
});

afterEach(() => {
  workspaceApi.getMyTasks.mockReset();
  document.body.replaceChildren();
});

describe("my tasks page", () => {
  it("shows the signed-in employee's real task summary and queue", async () => {
    const { container } = await renderPage();

    expect(container.textContent).toContain("我的任务");
    expect(container.textContent).toContain("任务概览");
    expect(container.textContent).toContain("全部任务");
    expect(container.textContent).toContain("待执行");
    expect(container.textContent).toContain("等待中");
    expect(container.textContent).toContain("处理中");
    expect(container.textContent).toContain("已结束");
    expect(container.textContent).toContain("DEMO-TASK-012");
    expect(container.textContent).toContain("已批准");
    expect(container.textContent).toContain("已发布");
    expect(container.textContent).toContain("青云镇 → 临港镇");
    expect(container.textContent).toContain("从青云镇出发，按国道-108行驶");
    expect(container.textContent).toContain("演示数据");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/dispatch/DEMO-TASK-012"]')?.textContent).toContain("查看详情");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/report-issue"]')?.textContent).toContain("提出问题");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/report-issue?taskId=DEMO-TASK-012"]')?.textContent).toContain("报告问题");
    expect(container.querySelector<HTMLAnchorElement>('a[href="/report-issue?taskId=DEMO-TASK-ENDED"]')).toBeNull();
    expect(container.textContent).not.toContain("数据接口尚未开放");
  });

  it("requests a server-filtered ready queue", async () => {
    const { container } = await renderPage();

    await click(container, "待执行");
    expect(workspaceApi.getMyTasks).toHaveBeenLastCalledWith({ limit: 20, state: "READY" }, expect.any(AbortSignal));
    expect([...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "待执行")?.getAttribute("aria-pressed")).toBe("true");
  });

  it.each([
    [new ApiError(403, "FORBIDDEN", "denied"), "没有查看我的任务的权限"],
    [new ApiError(503, "MY_TASKS_UNAVAILABLE", "down"), "我的任务服务暂不可用"],
    [new Error("network"), "我的任务加载失败"],
  ])("keeps failures explicit and retryable", async (error, title) => {
    workspaceApi.getMyTasks.mockRejectedValue(error);
    const { container } = await renderPage();

    expect(container.textContent).toContain(title);
    expect([...container.querySelectorAll("button")].some((button) => button.textContent === "重试")).toBe(true);
  });
});
