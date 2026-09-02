import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";

const workspaceApi = vi.hoisted(() => ({ getMyTasks: vi.fn() }));
const reportApi = vi.hoisted(() => ({ report: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://api.test",
    authenticationMode: "development_jwt",
  },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceApi }));
vi.mock("../src/services/api/anomaly-report-client", () => ({ anomalyReportClient: reportApi }));

import { ReportIssuePage } from "../src/pages/report-issue-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const taskPage = {
  items: [{
    row_id: 7,
    task_id: "TASK-OWNED",
    order_no: "ORD-OWNED",
    risk: "MEDIUM",
    description: "青云镇至临港镇配送",
    vehicle_id: "vehicle-001",
    original_route_id: "route-xinping",
    suggested_route_id: null,
    status: "IN_PROGRESS",
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:05:00Z",
    origin: "青云镇",
    destination: "临港镇",
    publication_status: "PENDING",
    published_at: null,
    route_instruction: null,
  }],
  summary: { total: 1, ready: 0, waiting: 0, active: 1, ended: 0 },
  total: 1,
  next_cursor: null,
  provenance: "LIVE" as const,
};

const accepted = {
  anomaly_id: 42,
  anomaly_no: "ANOM-example",
  task_id: "TASK-NEW",
  status: "PENDING",
  accepted: true,
  duplicate: false,
  message: "问题已上报，AI 调度已启动。",
};

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function renderPage() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter initialEntries={["/report-issue?taskId=TASK-OWNED"]}><ReportIssuePage /></MemoryRouter>);
  });
  await flush();
  return { container, root };
}

async function setField(container: HTMLElement, label: string, value: string) {
  const control = [...container.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>("input, textarea, select")]
    .find((item) => item.labels?.[0]?.textContent?.includes(label));
  if (!control) throw new Error(`Missing field: ${label}`);
  await act(async () => {
    const prototype = control instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : control instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(control, value);
    control.dispatchEvent(new Event(control instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

async function submit(container: HTMLElement) {
  const form = container.querySelector("form");
  if (!form) throw new Error("Missing report form");
  await act(async () => { form.requestSubmit(); });
  await flush();
}

beforeEach(() => {
  workspaceApi.getMyTasks.mockResolvedValue(taskPage);
  reportApi.report.mockResolvedValue(accepted);
});

afterEach(() => {
  workspaceApi.getMyTasks.mockReset();
  reportApi.report.mockReset();
  document.body.replaceChildren();
});

describe("report issue page", () => {
  it("submits a structured problem for the selected owned task", async () => {
    const { container } = await renderPage();
    const taskSelect = [...container.querySelectorAll("select")]
      .find((item) => item.labels?.[0]?.textContent?.includes("当前任务"));

    expect(container.querySelector("h1")?.textContent).toBe("提出配送问题");
    expect(taskSelect?.value).toBe("TASK-OWNED");
    expect(container.textContent).toContain("ORD-OWNED");
    expect(container.textContent).toContain("青云镇 → 临港镇");

    await setField(container, "问题描述", "车辆行驶时出现异响，无法继续安全行驶。");
    await setField(container, "当前位置", "新平路南段物流站入口");
    await setField(container, "问题类型", "VEHICLE_BREAKDOWN");
    await setField(container, "车辆状态", "BROKEN");
    await setField(container, "风险等级", "HIGH");
    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "TASK-OWNED",
      anomaly_type: "VEHICLE_BREAKDOWN",
      reported_vehicle_status: "BROKEN",
      severity: "HIGH",
    }));
    expect(container.textContent).toContain("ANOM-example");
    expect(container.textContent).toContain("TASK-NEW");
    expect(container.querySelector('a[href="/dispatch/TASK-NEW"]')).not.toBeNull();
  });

  it("keeps the saved report visible and retries queue startup", async () => {
    reportApi.report
      .mockRejectedValueOnce(new ApiError(
        503,
        "REPORT_QUEUE_UNAVAILABLE",
        "问题已保存，但 AI 调度暂未启动。请使用相同内容重试。",
        {
          anomaly_id: 42,
          anomaly_no: "ANOM-example",
          task_id: "TASK-SAVED",
          retryable: true,
        },
      ))
      .mockResolvedValueOnce({ ...accepted, task_id: "TASK-SAVED", duplicate: true });
    const { container } = await renderPage();
    await setField(container, "问题描述", "新平路连续降雨，路面明显湿滑。");
    await setField(container, "当前位置", "新平路北段");

    await submit(container);

    expect(container.textContent).toContain("问题已保存，但 AI 调度暂未启动");
    expect(container.textContent).toContain("TASK-SAVED");
    const retry = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "重试启动 AI 调度");
    expect(retry).toBeDefined();
    await act(async () => { retry?.click(); });
    await flush();

    expect(reportApi.report).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("问题已上报，AI 调度已启动");
  });
});
