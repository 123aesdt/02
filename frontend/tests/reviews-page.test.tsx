import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";

const workspaceApi = vi.hoisted(() => ({ getReviews: vi.fn() }));
const decisionApi = vi.hoisted(() => ({ decide: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceApi }));
vi.mock("../src/services/api/review-decision-client", () => ({ reviewDecisionClient: decisionApi }));

import { ReviewsPage } from "../src/pages/reviews-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const reviewPage = {
  items: [{
    row_id: 201,
    task_id: "DEMO-TASK-101",
    order_no: "DEMO-ORDER-101",
    risk: "HIGH",
    reason: "高风险异常需要人工复核",
    ai_analysis_reason: "员工上报右后轮爆胎，车辆无法继续行驶。",
    ai_recommended_action: "立即安全停车并设置警示标志，检查备胎条件并更换轮胎。",
    ai_analysis_mode: "EIGHT_AGENT_RULE_ASSISTED",
    issue_subtype: "TIRE",
    vehicle_id: "demo-vehicle-101",
    original_route_id: "青云乡道",
    suggested_route_id: null,
    status: "REVIEW_REQUIRED",
    created_at: "2026-08-30T08:00:00Z",
  }],
  total: 1,
  next_cursor: null,
  provenance: "DEMO" as const,
};

async function renderPage() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><ReviewsPage /></MemoryRouter>); });
  await flush();
  return { container, root };
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

async function click(container: HTMLElement, text: string) {
  const button = [...container.querySelectorAll("button")].find((item) => item.textContent?.trim() === text);
  if (!button) throw new Error(`Missing button: ${text}`);
  await act(async () => { button.click(); });
  return button as HTMLButtonElement;
}

async function enterReason(container: HTMLElement, value: string) {
  const textarea = container.querySelector<HTMLTextAreaElement>('textarea[aria-label="复核说明"]');
  if (!textarea) throw new Error("Missing review reason");
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  await act(async () => { setter?.call(textarea, value); textarea.dispatchEvent(new Event("input", { bubbles: true })); });
}

beforeEach(() => {
  workspaceApi.getReviews.mockResolvedValue(reviewPage);
  decisionApi.decide.mockResolvedValue({
    task_id: "DEMO-TASK-101",
    decision: "APPROVE",
    status: "APPROVED",
    reviewer: "王主管",
    decided_at: "2026-08-30T10:15:00Z",
    dispatch_version: 2,
  });
});

afterEach(() => {
  workspaceApi.getReviews.mockReset();
  decisionApi.decide.mockReset();
  document.body.replaceChildren();
});

describe("reviews page decisions", () => {
  it("shows real approve and reject actions for each review row", async () => {
    const { container } = await renderPage();

    expect(container.textContent).toContain("DEMO-TASK-101");
    expect([...container.querySelectorAll("button")].map((button) => button.textContent?.trim())).toEqual(
      expect.arrayContaining(["批准", "拒绝"]),
    );
    expect(container.textContent).not.toContain("不提供批准或拒绝动作");
  });

  it("shows 8-Agent analysis, action advice, and no fabricated route", async () => {
    const { container } = await renderPage();

    expect(container.textContent).toContain("AI 分析原因");
    expect(container.textContent).toContain("AI 处置建议");
    expect(container.textContent).toContain("员工上报右后轮爆胎");
    expect(container.textContent).toContain("更换轮胎");
    expect(container.textContent).toContain("当前不适用");
    expect(container.textContent).toContain("8-Agent 分析完成");
  });

  it("requires a second confirmation and refreshes the server list after approval", async () => {
    workspaceApi.getReviews
      .mockResolvedValueOnce(reviewPage)
      .mockResolvedValueOnce({ ...reviewPage, items: [], total: 0 });
    const { container } = await renderPage();

    await click(container, "批准");
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain("确认批准该调度方案");
    await enterReason(container, "同意按安全绕行方案执行");
    await click(container, "确认批准");
    await flush();

    expect(decisionApi.decide).toHaveBeenCalledWith("DEMO-TASK-101", {
      decision: "APPROVE",
      reason: "同意按安全绕行方案执行",
    });
    expect(workspaceApi.getReviews).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("任务已批准");
    expect(container.textContent).toContain("当前没有等待人工复核任务");
  });

  it("does not submit a rejection until a two-character reason is entered", async () => {
    const { container } = await renderPage();

    await click(container, "拒绝");
    const confirm = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "确认拒绝");
    expect(confirm?.disabled).toBe(true);
    await enterReason(container, "单");
    expect(confirm?.disabled).toBe(true);
    await enterReason(container, "信息不足");
    expect(confirm?.disabled).toBe(false);
  });

  it("keeps the task visible and explains a concurrent decision conflict", async () => {
    decisionApi.decide.mockRejectedValue(
      new ApiError(409, "REVIEW_ALREADY_DECIDED", "该任务已由其他人员处理，请刷新列表。"),
    );
    const { container } = await renderPage();

    await click(container, "批准");
    await click(container, "确认批准");
    await flush();

    expect(container.textContent).toContain("该任务已由其他人员处理，请刷新列表");
    expect(container.textContent).toContain("DEMO-TASK-101");
    expect(workspaceApi.getReviews).toHaveBeenCalledTimes(1);
  });
});
