import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";
import { fleetEdges, fleetRoutes } from "../src/features/fleet-sandbox/fleet-sandbox-data";

const workspaceApi = vi.hoisted(() => ({ getMyTasks: vi.fn() }));
const reportApi = vi.hoisted(() => ({ report: vi.fn() }));
const vehicleOperationsApi = vi.hoisted(() => ({ getDriverOperationSnapshot: vi.fn() }));
const demoScenarioApi = vi.hoisted(() => ({ reset: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://api.test",
    authenticationMode: "development_jwt",
  },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceApi }));
vi.mock("../src/services/api/anomaly-report-client", () => ({ anomalyReportClient: reportApi }));
vi.mock("../src/services/api/vehicle-operations-client", () => ({ vehicleOperationsClient: vehicleOperationsApi }));
vi.mock("../src/services/api/demo-scenario-client", () => ({ demoScenarioClient: demoScenarioApi }));

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
    can_report_anomaly: true,
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
    can_report_anomaly: true,
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
    await new Promise((resolve) => window.setTimeout(resolve, 0));
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
  vehicleOperationsApi.getDriverOperationSnapshot.mockRejectedValue(new Error("not found"));
  demoScenarioApi.reset.mockResolvedValue({
    scenario_id: "VEHICLE_BREAKDOWN_N04",
    status: "READY",
    message: "演示场景已恢复，可以再次提交。",
  });
});

afterEach(() => {
  workspaceApi.getMyTasks.mockReset();
  reportApi.report.mockReset();
  vehicleOperationsApi.getDriverOperationSnapshot.mockReset();
  demoScenarioApi.reset.mockReset();
  document.body.replaceChildren();
});

describe("report issue page", () => {
  it("does not guess a vehicle when the employee has no fixed assignment", async () => {
    workspaceApi.getMyTasks.mockResolvedValue({
      ...taskPage,
      items: [{
        ...fleetSourceTasks[19],
        task_id: "TASK-LEGACY-V020",
      }],
      summary: { total: 1, ready: 0, waiting: 0, active: 1, ended: 0 },
      total: 1,
    });

    const { container } = await renderPage();

    expect((container.querySelector("#report-vehicle") as HTMLInputElement).value).toBe("暂无固定车辆");
    expect(container.textContent).toContain("请联系调度中心为当前员工绑定车辆");
    expect(container.querySelector("[data-driver-route-map]")).toBeNull();
  });

  it("locks the employee to one vehicle and auto-fills its task, route, position, and map", async () => {
    const { container } = await renderPage();

    expect(container.querySelector("select#report-vehicle")).toBeNull();
    expect(container.querySelector('[data-provenance="LIVE"]')?.textContent).toContain("实时业务数据");
    expect(container.textContent).toContain("本人任务与车辆绑定来自后端 API");
    const vehicle = container.querySelector<HTMLInputElement>("#report-vehicle");
    expect(vehicle?.value).toBe("车辆-001");
    expect(vehicle?.readOnly).toBe(true);
    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-001｜运单-001");
    expect((container.querySelector("#report-source-task") as HTMLInputElement).readOnly).toBe(true);
    expect((container.querySelector("#report-route") as HTMLInputElement).value).toBe("路线-01 · 调度中心—快递集散线");
    expect((container.querySelector("#report-route") as HTMLInputElement).readOnly).toBe(true);
    expect((container.querySelector("#report-location") as HTMLInputElement).value.length).toBeGreaterThan(3);
    expect((container.querySelector("#report-location") as HTMLInputElement).readOnly).toBe(true);
    const map = container.querySelector<HTMLElement>('[data-driver-route-map][data-route-id="ROUTE-01"]');
    expect(map).not.toBeNull();
    expect(map?.tagName).not.toBe("svg");
    expect(map?.dataset.mapContract).toBe("AMAP_ROAD_V1");
    expect(map?.dataset.routeNodeIds).toBe("N19,N01,N03,N22,N20,N05,N06");
    expect(map?.dataset.currentVehicleId).toBe("V-001");
    expect(container.textContent).not.toContain("DEMO-TASK-REPORT-020");
    expect(container.textContent).not.toContain("DEMO-REPORT-ORDER-020");
  });

  it("submits from the employee fixed vehicle and shared simulated position", async () => {
    const { container } = await renderPage();

    expect(container.querySelector("select#report-vehicle")).toBeNull();
    expect((container.querySelector("#report-vehicle") as HTMLInputElement).value).toBe("车辆-001");
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
      source_task_id: "TASK-OWNED",
      location_text: location?.value,
      incident_node_id: expect.stringMatching(/^N\d{2}$/),
    }));
    const syncState = container.querySelector('[data-driver-sync-state="ACCEPTED"]');
    expect(syncState).not.toBeNull();
    expect(syncState?.textContent).toContain("后端已接收");
    expect(syncState?.textContent).toContain("AI 调度已启动");
    expect(syncState?.textContent).toContain("管理端将在 1 秒内同步");
  });

  it("applies the fixed vehicle-breakdown scenario and submits its node id", async () => {
    const { container } = await renderPage();

    await setField(container, "演示异常场景", "VEHICLE_BREAKDOWN_N04");

    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-001｜运单-001");
    expect((container.querySelector("#report-location") as HTMLSelectElement).value).toBe("新平路 K3.2");
    expect((container.querySelector("#report-description") as HTMLTextAreaElement).value).toBe("车辆-001 在新平路 K3.2 发动机故障，无法继续配送。");

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "TASK-OWNED",
      anomaly_type: "VEHICLE_BREAKDOWN",
      reported_vehicle_status: "BROKEN",
      severity: "HIGH",
      incident_node_id: "N04",
      affected_edge_id: null,
    }));
  });

  it("resets a completed demo and submits the next run as a new task", async () => {
    const { container } = await renderPage();
    await setField(container, "演示异常场景", "VEHICLE_BREAKDOWN_N04");
    await submit(container);

    const firstKey = reportApi.report.mock.calls[0][0].idempotency_key;
    const resetButton = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "重新演示");
    expect(resetButton).toBeDefined();

    await act(async () => { resetButton?.click(); });
    await flush();

    expect(demoScenarioApi.reset).toHaveBeenCalledWith("VEHICLE_BREAKDOWN_N04");
    expect(container.textContent).toContain("演示场景已恢复，可以再次提交。");
    expect(container.textContent).not.toContain("查看 AI 调度进度");
    expect((container.querySelector(".anomaly-report-form fieldset") as HTMLFieldSetElement).disabled).toBe(false);

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledTimes(2);
    const secondKey = reportApi.report.mock.calls[1][0].idempotency_key;
    expect(secondKey).not.toBe(firstKey);
  });

  it("keeps the completed result visible when demo reset fails", async () => {
    demoScenarioApi.reset.mockRejectedValue(new ApiError(
      409,
      "DEMO_SCENARIO_STATE_INCOMPLETE",
      "复位失败",
    ));
    const { container } = await renderPage();
    await setField(container, "演示异常场景", "VEHICLE_BREAKDOWN_N04");
    await submit(container);

    const resetButton = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "重新演示");
    await act(async () => { resetButton?.click(); });
    await flush();

    expect(container.textContent).toContain("复位失败");
    expect(container.textContent).toContain("查看 AI 调度进度");
  });

  it("applies the fixed road-blocked scenario and submits its edge id", async () => {
    const { container } = await renderPage();

    await setField(container, "演示异常场景", "ROAD_BLOCKED_E04");

    expect((container.querySelector("#report-source-task") as HTMLInputElement).value).toBe("配送任务-001｜运单-001");
    expect((container.querySelector("#report-location") as HTMLSelectElement).value).toBe("新平路东河桥段");
    expect((container.querySelector("#report-description") as HTMLTextAreaElement).value).toBe("新平路东河桥段发生塌方，车辆无法通行。");

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "TASK-OWNED",
      anomaly_type: "ROAD_BLOCKED",
      reported_vehicle_status: "NORMAL",
      severity: "HIGH",
      incident_node_id: null,
      affected_edge_id: "E04",
    }));
  });

  it("keeps scenario controls disabled until the fixed task and route are ready", async () => {
    let resolveTasks!: (value: typeof taskPage) => void;
    workspaceApi.getMyTasks.mockReturnValue(new Promise((resolve) => {
      resolveTasks = resolve;
    }));
    const { container } = await renderPage();

    expect((container.querySelector(".anomaly-report-form fieldset") as HTMLFieldSetElement).disabled).toBe(true);

    await act(async () => {
      resolveTasks(taskPage);
    });
    await flush();

    expect((container.querySelector(".anomaly-report-form fieldset") as HTMLFieldSetElement).disabled).toBe(false);
  });

  it("blocks an edge on route 03 so recalculation produces a real detour", async () => {
    workspaceApi.getMyTasks.mockResolvedValue({
      ...taskPage,
      items: [{
        ...fleetSourceTasks[4],
        original_route_id: null,
      }],
      summary: { total: 1, ready: 0, waiting: 0, active: 1, ended: 0 },
      total: 1,
    });
    const { container } = await renderPage();

    await setField(container, "演示异常场景", "ROAD_BLOCKED_E04");

    expect((container.querySelector("#report-location") as HTMLSelectElement).value).toBe("中心仓至 308 线");
    expect((container.querySelector("#report-description") as HTMLTextAreaElement).value).toBe("中心仓至 308 线发生塌方，车辆需要绕行。");
    const route = fleetRoutes.find((item) => item.id === "ROUTE-03");
    const edge = fleetEdges.find((item) => item.id === "E10");
    expect(route).toBeDefined();
    expect(edge).toBeDefined();
    expect(route?.nodeIds.slice(0, -1).some((nodeId, index) => {
      const nextNodeId = route.nodeIds[index + 1];
      return (edge?.from === nodeId && edge.to === nextNodeId) || (edge?.to === nodeId && edge.from === nextNodeId);
    })).toBe(true);

    await submit(container);

    expect(reportApi.report).toHaveBeenCalledWith(expect.objectContaining({
      source_task_id: "DEMO-TASK-REPORT-005",
      anomaly_type: "ROAD_BLOCKED",
      affected_edge_id: "E10",
    }));
  });

  it("keeps manual problem type and vehicle status consistent", async () => {
    const { container } = await renderPage();

    await setField(container, "问题类型", "VEHICLE_BREAKDOWN");
    const vehicleStatus = container.querySelector<HTMLSelectElement>("#report-vehicle-status");
    expect(vehicleStatus?.value).toBe("BROKEN");

    await setField(container, "问题类型", "WEATHER");
    expect(vehicleStatus?.value).toBe("NORMAL");
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

  it("does not show rescue and repair progress before a vehicle breakdown is submitted", async () => {
    const { container } = await renderPage();
    await flush();

    expect(vehicleOperationsApi.getDriverOperationSnapshot).not.toHaveBeenCalled();
    expect(container.querySelector("[data-driver-operation-status]")).toBeNull();
    expect(container.querySelector("#driver-operation-progress")).toBeNull();
  });

  it("shows read-only rescue and repair progress for the accepted breakdown task", async () => {
    vehicleOperationsApi.getDriverOperationSnapshot.mockResolvedValue({
      task_id: "TASK-NEW",
      generated_at: "2026-09-11T10:00:00Z",
      incident: { status: "AUTO_PROCESSING", risk: "HIGH", vehicle_id: "V-001", replacement_vehicle_id: "V-005", location_node_id: "N04", fault_code: "ENGINE_OVERHEAT", cargo: "冷链生鲜" },
      nodes: [], edges: [], vehicles: [], routes: [],
      timeline: Array.from({ length: 6 }, (_, index) => ({
        event_id: `EVENT-${index + 1}`,
        event_type: index === 0 ? "VEHICLE_STOPPED" : "RESCUE_EVENT",
        label: index === 0 ? "发现故障，车辆已安全停车" : `处置事件 ${index + 1}`,
        timestamp: `2026-09-11T10:0${index}:00Z`,
        payload: {},
      })),
      rescue: { mission_no: "RM-001", status: "DELIVERED", progress_percent: 100, rescue_unit_id: "RU-001", incident_node_id: "N04", station_node_id: "N15", next_transition_at: null },
      maintenance: { order_no: "MO-001", vehicle_id: "V-001", bay_code: "B-02", status: "SCHEDULED", fault_code: "ENGINE_OVERHEAT", diagnosis: "不应提前展示的诊断", repair_minutes: 30, manual_inspection_required: true, inspection_result: null, progress_percent: 0, countdown_seconds: null, available_after: null },
      stages: [
        { key: "SAFE_STOP", title: "安全停车", status: "COMPLETED", detail: "已完成" },
        { key: "RESCUE", title: "救援运送", status: "COMPLETED", detail: "救援进度 100%" },
        { key: "MAINTENANCE", title: "维修与自动复岗", status: "WAITING", detail: "维修工单已预约" },
      ],
    });

    const { container } = await renderPage();
    await setField(container, "演示异常场景", "VEHICLE_BREAKDOWN_N04");
    await submit(container);
    await flush();

    expect(vehicleOperationsApi.getDriverOperationSnapshot).toHaveBeenCalledWith("TASK-NEW");
    expect(container.querySelector("[data-driver-operation-status]")).not.toBeNull();
    const employeeTimeline = container.querySelector('[data-vehicle-operation-timeline][data-context="employee"]');
    expect(employeeTimeline).not.toBeNull();
    expect(employeeTimeline?.querySelectorAll("[data-operation-stage]")).toHaveLength(3);
    expect(employeeTimeline?.textContent).toContain("维修与自动复岗");
    expect(container.textContent).toContain("故障车辆已送达维修站");
    expect(container.textContent).toContain("维修工位已预约");
    expect(container.textContent).not.toContain("不应提前展示的诊断");
    expect(container.textContent).toContain("发现故障，车辆已安全停车");
    expect(container.textContent).toContain("预计恢复");
    expect(container.querySelector("button")?.textContent).not.toContain("质检");
  });
});
