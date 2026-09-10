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

const fleetSourceTasks = Array.from({ length: 20 }, (_, index) => {
  const vehicleNumber = index + 1;
  const vehicleSequence = String(vehicleNumber).padStart(3, "0");
  const routeSequence = String(Math.floor(index / 2) + 1).padStart(2, "0");
  return {
    row_id: 100 + vehicleNumber,
    task_id: vehicleNumber === 1 ? "DEMO-TASK-REPORT-VEHICLE" : vehicleNumber === 8 ? "DEMO-TASK-REPORT-ROAD" : `DEMO-TASK-REPORT-${vehicleSequence}`,
    order_no: `DEMO-REPORT-ORDER-${vehicleSequence}`,
    risk: null,
    description: null,
    vehicle_id: `V-${vehicleSequence}`,
    original_route_id: `ROUTE-${routeSequence}`,
    suggested_route_id: null,
    status: "IN_PROGRESS",
    created_at: `2026-09-01T08:${vehicleSequence.slice(1)}:00Z`,
    updated_at: `2026-09-01T08:${vehicleSequence.slice(1)}:00Z`,
    origin: "新平县中心仓",
    destination: "县域配送站",
    publication_status: "PENDING",
    published_at: null,
    route_instruction: null,
  };
});

const taskPage = {
  items: [...fleetSourceTasks, {
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
  summary: { total: 21, ready: 0, waiting: 0, active: 21, ended: 0 },
  total: 21,
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
  it("lists twenty unique Chinese vehicle numbers and auto-fills task, route, position, and map", async () => {
    const { container } = await renderPage();

    const vehicleSelect = container.querySelector<HTMLSelectElement>("#report-vehicle");
    const vehicleOptions = vehicleSelect?.querySelectorAll("option[data-vehicle-id]");
    expect(vehicleOptions).toHaveLength(20);
    expect([...vehicleOptions ?? []].map((option) => option.textContent)).toEqual(Array.from({ length: 20 }, (_, index) => `车辆-${String(index + 1).padStart(3, "0")}`));

    await setField(container, "选择上报车辆", "V-020");

    expect(vehicleSelect?.value).toBe("V-020");
    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-020｜运单-020");
    expect((container.querySelector("#report-source-task") as HTMLInputElement).readOnly).toBe(true);
    expect((container.querySelector("#report-route") as HTMLInputElement).value).toBe("路线-10 · 维修救援接驳线");
    expect((container.querySelector("#report-route") as HTMLInputElement).readOnly).toBe(true);
    expect((container.querySelector("#report-location") as HTMLInputElement).value.length).toBeGreaterThan(3);
    expect((container.querySelector("#report-location") as HTMLInputElement).readOnly).toBe(true);
    const map = container.querySelector<SVGElement>('[data-driver-route-map][data-route-id="ROUTE-10"]');
    expect(map).not.toBeNull();
    expect(map?.querySelectorAll("[data-driver-route-line]")).toHaveLength(1);
    expect(map?.querySelector('[data-fleet-vehicle-id="V-020"]')).not.toBeNull();
    expect(container.textContent).not.toContain("DEMO-TASK-REPORT-020");
    expect(container.textContent).not.toContain("DEMO-REPORT-ORDER-020");
  });

  it("selects a reportable vehicle, switches its task, and fills the shared simulated position", async () => {
    const { container } = await renderPage();

    const vehicleSelect = container.querySelector<HTMLSelectElement>("#report-vehicle");
    expect(vehicleSelect).not.toBeNull();
    expect(vehicleSelect?.textContent).toContain("车辆-001");
    expect(vehicleSelect?.textContent).toContain("车辆-008");

    await setField(container, "选择上报车辆", "V-001");

    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-001｜运单-001");
    const location = container.querySelector<HTMLInputElement>("#report-location");
    expect(location?.readOnly).toBe(true);
    expect(location?.value.length).toBeGreaterThan(3);
    expect(container.textContent).toContain("车辆位置来自管理员地图同一套虚拟沙盘");

    await setField(container, "问题描述", "车辆发动机故障，已经无法继续安全行驶。");
    await setField(container, "问题类型", "VEHICLE_BREAKDOWN");
    await setField(container, "车辆状态", "BROKEN");
    await setField(container, "风险等级", "HIGH");
    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "DEMO-TASK-REPORT-VEHICLE",
      location_text: location?.value,
      incident_node_id: expect.stringMatching(/^N\d{2}$/),
    }));
  });

  it("applies the fixed vehicle-breakdown scenario and submits its node id", async () => {
    const { container } = await renderPage();

    await setField(container, "演示异常场景", "VEHICLE_BREAKDOWN_N04");

    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-001｜运单-001");
    expect((container.querySelector("#report-location") as HTMLSelectElement).value).toBe("新平路 K3.2");
    expect((container.querySelector("#report-description") as HTMLTextAreaElement).value).toBe("新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。");

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "DEMO-TASK-REPORT-VEHICLE",
      anomaly_type: "VEHICLE_BREAKDOWN",
      reported_vehicle_status: "BROKEN",
      severity: "HIGH",
      incident_node_id: "N04",
      affected_edge_id: null,
    }));
  });

  it("applies the fixed road-blocked scenario and submits its edge id", async () => {
    const { container } = await renderPage();

    await setField(container, "演示异常场景", "ROAD_BLOCKED_E04");

    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-008｜运单-008");
    expect((container.querySelector("#report-location") as HTMLSelectElement).value).toBe("新平路东河桥段");
    expect((container.querySelector("#report-description") as HTMLTextAreaElement).value).toBe("新平路东河桥段发生塌方，车辆无法通行。");

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "DEMO-TASK-REPORT-ROAD",
      anomaly_type: "ROAD_BLOCKED",
      reported_vehicle_status: "NORMAL",
      severity: "HIGH",
      incident_node_id: null,
      affected_edge_id: "E04",
    }));
  });

  it("submits a structured problem for the selected owned task", async () => {
    const { container } = await renderPage();
    const taskDisplay = container.querySelector<HTMLInputElement>("#report-source-task");

    expect(container.querySelector("h1")?.textContent).toBe("提出配送问题");
    expect(taskDisplay?.value).toBe("配送任务-001｜运单-001");
    expect(container.textContent).not.toContain("TASK-OWNED");
    expect(container.textContent).not.toContain("ORD-OWNED");
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
    expect(container.textContent).toContain("异常-042");
    expect(container.textContent).toContain("调度任务-042");
    expect(container.textContent).not.toContain("ANOM-example");
    expect(container.textContent).not.toContain("TASK-NEW");
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
    expect(container.textContent).toContain("异常-042");
    expect(container.textContent).toContain("调度任务-042");
    expect(container.textContent).not.toContain("TASK-SAVED");
    const retry = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "重试启动 AI 调度");
    expect(retry).toBeDefined();
    await act(async () => { retry?.click(); });
    await flush();

    expect(reportApi.report).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("问题已上报，AI 调度已启动");
  });
});
