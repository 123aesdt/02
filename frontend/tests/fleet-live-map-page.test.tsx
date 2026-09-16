import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({ getAnomalies: vi.fn() }));
const taskApi = vi.hoisted(() => ({ getTaskStatus: vi.fn(), getTaskResult: vi.fn() }));
const ticketApi = vi.hoisted(() => ({ issueTaskWsTicket: vi.fn() }));
const operationApi = vi.hoisted(() => ({ getMapSnapshot: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));
vi.mock("../src/services/dispatch-service", () => taskApi);
vi.mock("../src/services/api/ws-ticket-client", () => ticketApi);
vi.mock("../src/services/api/vehicle-operations-client", () => ({ vehicleOperationsClient: operationApi }));

import { setAuthenticatedSession, clearSession } from "../src/auth/session";
import { FleetLiveMapPage } from "../src/pages/fleet-live-map-page";
import { demoVehicleOperationSnapshot } from "../src/features/fleet-sandbox/vehicle-operation-demo";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const now = "2026-09-16T10:00:00Z";

class FakeWebSocket {
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close() { this.onclose?.({ code: 1000 } as CloseEvent); }
}

const nodes = [
  { node_id: "N01", name: "新平县中心仓", x_km: "0.00", y_km: "0.00", node_type: "STATION" },
  { node_id: "N02", name: "西环路口", x_km: "2.00", y_km: "0.00", node_type: "JUNCTION" },
  { node_id: "N04", name: "故障点", x_km: "5.00", y_km: "2.00", node_type: "INCIDENT_POINT" },
  { node_id: "N06", name: "城东配送站", x_km: "10.00", y_km: "2.00", node_type: "STATION" },
  { node_id: "N08", name: "102 国道中段", x_km: "6.00", y_km: "-2.00", node_type: "JUNCTION" },
  { node_id: "N15", name: "县域车辆维修站", x_km: "4.00", y_km: "1.00", node_type: "STATION" },
];

const edges = [
  { edge_id: "E04", name: "堵塞道路", from_node_id: "N02", to_node_id: "N04", distance_km: "2.50", base_minutes: 5, road_level: "COUNTY", risk_level: "HIGH", status: "BLOCKED", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 18 },
  { edge_id: "E07", name: "新规划道路", from_node_id: "N02", to_node_id: "N08", distance_km: "4.00", base_minutes: 7, road_level: "NATIONAL", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "20.00", bidirectional: true, version: 18 },
  { edge_id: "E09", name: "配送站连接线", from_node_id: "N08", to_node_id: "N06", distance_km: "2.50", base_minutes: 4, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "8.00", bidirectional: true, version: 18 },
  { edge_id: "E20", name: "维修站接驳线", from_node_id: "N15", to_node_id: "N04", distance_km: "2.80", base_minutes: 6, road_level: "TOWN", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "5.00", bidirectional: true, version: 18 },
];

const routePlan = {
  original_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N04"], edge_ids: ["E04"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "16", visited_node_count: 6, scoring_formula: null },
  recommended_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N08", "N06"], edge_ids: ["E07", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0", visited_node_count: 8, scoring_formula: "ROUTE_SCORE_V1" },
  candidate_routes: [], blocked_edge_ids: ["E04"], distance_delta_km: "3.20", eta_delta_minutes: 4, visited_node_count: 8, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 18, network_nodes: nodes, network_edges: edges,
};

const resultByTask = {
  "TASK-ROAD": {
    task_id: "TASK-ROAD", order_id: 15, ready: true, status: "COMPLETED", anomaly_type: "ROAD_BLOCKED", dispatch: null, audit: null,
    vehicle_allocation: { original_vehicle_id: "V-008", target_vehicle_id: null, target_driver_id: null, vehicle_reassigned: false, candidate_vehicles: [], pickup_route: null, scoring_formula: "FLEET_SCORE_V1" },
    route_plan: routePlan,
  },
  "TASK-FAULT": {
    task_id: "TASK-FAULT", order_id: 16, ready: true, status: "COMPLETED", anomaly_type: "VEHICLE_BREAKDOWN", dispatch: null, audit: null,
    vehicle_allocation: { original_vehicle_id: "V-001", target_vehicle_id: "V-005", target_driver_id: "D-003", vehicle_reassigned: true, candidate_vehicles: [], pickup_route: { objective: "FASTEST", node_ids: ["N15", "N04"], edge_ids: ["E20"], distance_km: "2.80", estimated_minutes: 6, risk_cost: "0", visited_node_count: 2, scoring_formula: null }, scoring_formula: "FLEET_SCORE_V1" },
    route_plan: routePlan,
    dispatch_impact: {
      incident_vehicle_id: "V-001", replacement_vehicle_id: "V-005", replacement_driver_id: "D-003",
      pickup_distance_km: "2.80", pickup_eta_minutes: 6,
      route_distance_delta_km: "3.20", route_eta_delta_minutes: 4,
      total_distance_delta_km: "6.00", total_delay_minutes: 10,
      calculation_status: "CALCULATED",
    },
  },
} as const;

async function renderPage(): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><FleetLiveMapPage /></MemoryRouter>); });
  return { root, container };
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  ticketApi.issueTaskWsTicket.mockResolvedValue("ticket");
  operationApi.getMapSnapshot.mockResolvedValue({
    ...demoVehicleOperationSnapshot,
    task_id: "TASK-FAULT",
    routes: [
      { kind: "REPLACEMENT", edge_ids: ["E21", "E03", "E04"], node_ids: ["N15", "N19", "N01", "N03", "N04"], status: "ACTIVE" },
      { kind: "RESCUE", edge_ids: ["E22", "E04"], node_ids: ["N22", "N03", "N04"], status: "DISPATCHED" },
      { kind: "TOW", edge_ids: ["E20"], node_ids: ["N04", "N15"], status: "WAITING" },
      { kind: "INTERRUPTED", edge_ids: ["E04"], node_ids: ["N03", "N04"], status: "INTERRUPTED" },
    ],
  });
  workspaceReadApi.getAnomalies.mockResolvedValue({
    items: [
      { row_id: 2, anomaly_no: "ANOM-ROAD", order_no: "ORD-15", driver_id: "D-008", vehicle_id: "V-008", route_id: "R-1", latest_task_id: "TASK-ROAD", anomaly_type: "ROAD_BLOCKED", risk: "HIGH", description: "东河桥段堵塞", status: "COMPLETED", reported_at: "2026-09-09T09:28:45Z" },
      { row_id: 1, anomaly_no: "ANOM-FAULT", order_no: "ORD-16", driver_id: "D-001", vehicle_id: "V-001", route_id: "R-2", latest_task_id: "TASK-FAULT", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "车辆无法行驶", status: "COMPLETED", reported_at: "2026-09-09T09:20:00Z" },
    ], total: 2, next_cursor: null, provenance: "LIVE",
  });
  taskApi.getTaskStatus.mockImplementation(async (taskId: "TASK-ROAD" | "TASK-FAULT") => ({ task_id: taskId, order_id: taskId === "TASK-ROAD" ? 15 : 16, status: "COMPLETED", started_at: null, completed_at: "2026-09-09T09:29:00Z", created_at: "2026-09-09T09:28:45Z", ready: true, requires_manual_review: false }));
  taskApi.getTaskResult.mockImplementation(async (taskId: keyof typeof resultByTask) => resultByTask[taskId]);
  setAuthenticatedSession("admin-token", { subject_id: "CF-DEMO-005", display_name: "系统管理员", roles: ["ADMIN"], permissions: ["dispatch:read", "dispatch:review", "system:admin"], auth_method: "development_jwt", issued_at: "2026-09-09T09:00:00Z", expires_at: "2099-09-09T10:00:00Z" });
});

afterEach(() => {
  vi.useRealTimers();
  workspaceReadApi.getAnomalies.mockReset();
  taskApi.getTaskStatus.mockReset();
  taskApi.getTaskResult.mockReset();
  ticketApi.issueTaskWsTicket.mockReset();
  operationApi.getMapSnapshot.mockReset();
  clearSession();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("administrator fleet live map page", () => {
  it("shows a dedicated command-map skeleton without flashing legacy vehicles while task details load", async () => {
    const pendingStatus = deferred<Awaited<ReturnType<typeof taskApi.getTaskStatus>>>();
    taskApi.getTaskStatus.mockReturnValue(pendingStatus.promise);

    const view = await renderPage();
    await flush();

    expect(view.container.querySelector(".fleet-command-loading")).not.toBeNull();
    expect(view.container.querySelector("[data-fleet-vehicle-id]")).toBeNull();
    expect(view.container.querySelector(".fleet-sandbox")).toBeNull();
    expect(view.container.textContent).toContain("车辆与路线数据加载中");

    pendingStatus.resolve({
      task_id: "TASK-ROAD",
      order_id: 15,
      status: "COMPLETED",
      started_at: null,
      completed_at: "2026-09-09T09:29:00Z",
      created_at: "2026-09-09T09:28:45Z",
      ready: true,
      requires_manual_review: false,
    });
    await flush();
    await act(async () => { view.root.unmount(); });
  });

  it("prefers the most recent backend anomaly instead of an old demo task", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [
        { row_id: 40, anomaly_no: "ANOM-NEW", order_no: "ORD-40", driver_id: "D-001", vehicle_id: "V-001", route_id: "ROUTE-01", latest_task_id: "TASK-FAULT", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "最近故障", status: "OPEN", reported_at: "2026-09-11T09:20:00Z" },
        { row_id: 4, anomaly_no: "DEMO-ANOM-004", order_no: "DEMO-ORDER-004", driver_id: "D-001", vehicle_id: "V-001", route_id: "ROUTE-01", latest_task_id: "DEMO-TASK-REPORT-VEHICLE", anomaly_type: "vehicle_breakdown", risk: "HIGH", description: "完整救援演示", status: "OPEN", reported_at: "2026-09-09T09:20:00Z" },
      ], total: 2, next_cursor: null, provenance: "DEMO",
    });
    taskApi.getTaskStatus.mockImplementation(async (taskId: string) => ({ task_id: taskId, order_id: 16, status: "COMPLETED", started_at: null, completed_at: "2026-09-09T09:29:00Z", created_at: "2026-09-09T09:28:45Z", ready: true, requires_manual_review: false }));
    taskApi.getTaskResult.mockResolvedValue({ ...resultByTask["TASK-FAULT"], task_id: "DEMO-TASK-REPORT-VEHICLE", anomaly_type: "vehicle_breakdown" });

    const view = await renderPage();
    await flush();

    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]')?.value).toBe("TASK-FAULT");
    await act(async () => { view.root.unmount(); });
  });

  it("announces a newly reported driver issue, selects its task, and opens the incident vehicle", async () => {
    const view = await renderPage();
    await flush();

    expect(view.container.querySelector("[data-live-driver-report]")).toBeNull();
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [
        { row_id: 13, anomaly_no: "ANOM-LIVE", order_no: "ORD-13", driver_id: "D-013", vehicle_id: "V-013", route_id: "ROUTE-07", latest_task_id: "TASK-LIVE", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "司机上报制动系统故障", status: "PENDING", reported_at: "2026-09-16T10:00:00Z" },
        { row_id: 2, anomaly_no: "ANOM-ROAD", order_no: "ORD-15", driver_id: "D-008", vehicle_id: "V-008", route_id: "R-1", latest_task_id: "TASK-ROAD", anomaly_type: "ROAD_BLOCKED", risk: "HIGH", description: "东河桥段堵塞", status: "COMPLETED", reported_at: "2026-09-09T09:28:45Z" },
        { row_id: 1, anomaly_no: "ANOM-FAULT", order_no: "ORD-16", driver_id: "D-001", vehicle_id: "V-001", route_id: "R-2", latest_task_id: "TASK-FAULT", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "车辆无法行驶", status: "COMPLETED", reported_at: "2026-09-09T09:20:00Z" },
      ], total: 3, next_cursor: null, provenance: "LIVE",
    });
    taskApi.getTaskStatus.mockImplementation(async (taskId: string) => ({ task_id: taskId, order_id: 13, status: taskId === "TASK-LIVE" ? "RUNNING" : "COMPLETED", started_at: "2026-09-16T10:00:01Z", completed_at: taskId === "TASK-LIVE" ? null : "2026-09-09T09:29:00Z", created_at: "2026-09-16T10:00:00Z", ready: true, requires_manual_review: false }));
    taskApi.getTaskResult.mockImplementation(async (taskId: string) => taskId === "TASK-LIVE" ? {
      ...resultByTask["TASK-FAULT"],
      task_id: "TASK-LIVE",
      status: "RUNNING",
      vehicle_allocation: { ...resultByTask["TASK-FAULT"].vehicle_allocation, original_vehicle_id: "V-013", target_vehicle_id: "V-015" },
      dispatch_impact: { ...resultByTask["TASK-FAULT"].dispatch_impact, incident_vehicle_id: "V-013", replacement_vehicle_id: "V-015" },
    } : resultByTask[taskId as keyof typeof resultByTask]);

    const refresh = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent?.includes("刷新"));
    await act(async () => { refresh?.click(); });
    await flush();
    await flush();

    const alert = view.container.querySelector("[data-live-driver-report]");
    expect(alert).not.toBeNull();
    expect(alert?.textContent).toContain("司机问题已同步");
    expect(alert?.textContent).toContain("D-013");
    expect(alert?.textContent).toContain("V-013");
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]')?.value).toBe("TASK-LIVE");
    expect(view.container.querySelector('[data-fleet-vehicle-detail="V-013"]')).not.toBeNull();

    const dismiss = view.container.querySelector<HTMLButtonElement>('button[aria-label="关闭司机上报提醒"]');
    await act(async () => { dismiss?.click(); });
    expect(view.container.querySelector("[data-live-driver-report]")).toBeNull();
    expect(view.container.querySelector('[data-fleet-vehicle-detail="V-013"]')).not.toBeNull();
    expect(view.container.querySelector<HTMLButtonElement>('button[aria-label="停止跟随车辆"]')?.getAttribute("aria-pressed")).toBe("true");
    await act(async () => { view.root.unmount(); });
  });

  it("treats the first task after an empty baseline as a new driver report on the first one-second poll", async () => {
    vi.useFakeTimers();
    workspaceReadApi.getAnomalies
      .mockResolvedValueOnce({ items: [], total: 0, next_cursor: null, provenance: "LIVE" })
      .mockResolvedValue({
        items: [
          { row_id: 13, anomaly_no: "ANOM-FIRST", order_no: "ORD-13", driver_id: "D-013", vehicle_id: "V-013", route_id: "ROUTE-07", latest_task_id: "TASK-FIRST", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "首辆司机上报车辆故障", status: "PENDING", reported_at: "2026-09-16T10:00:00Z" },
        ], total: 1, next_cursor: null, provenance: "LIVE",
      });
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-FIRST", order_id: 13, status: "RUNNING", started_at: now, completed_at: null, created_at: now, ready: true, requires_manual_review: false });
    taskApi.getTaskResult.mockResolvedValue({
      ...resultByTask["TASK-FAULT"],
      task_id: "TASK-FIRST",
      status: "RUNNING",
      vehicle_allocation: { ...resultByTask["TASK-FAULT"].vehicle_allocation, original_vehicle_id: "V-013", target_vehicle_id: "V-015" },
      dispatch_impact: { ...resultByTask["TASK-FAULT"].dispatch_impact, incident_vehicle_id: "V-013", replacement_vehicle_id: "V-015" },
    });

    const view = await renderPage();
    await flush();
    expect(view.container.querySelector("[data-live-driver-report]")).toBeNull();
    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(999); });
    expect(workspaceReadApi.getAnomalies).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    await flush();
    await flush();

    expect(view.container.querySelector("[data-live-driver-report]")?.textContent).toContain("首辆司机上报车辆故障");
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]')?.value).toBe("TASK-FIRST");
    expect(view.container.querySelector('[data-fleet-vehicle-detail="V-013"]')).not.toBeNull();
    await act(async () => { view.root.unmount(); });
  });

  it("queues every task when several driver reports arrive in the same poll", async () => {
    const view = await renderPage();
    await flush();
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [
        { row_id: 14, anomaly_no: "ANOM-LIVE-14", order_no: "ORD-14", driver_id: "D-014", vehicle_id: "V-014", route_id: "ROUTE-08", latest_task_id: "TASK-LIVE-14", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "司机十四上报车辆故障", status: "PENDING", reported_at: "2026-09-16T10:00:01Z" },
        { row_id: 13, anomaly_no: "ANOM-LIVE-13", order_no: "ORD-13", driver_id: "D-013", vehicle_id: "V-013", route_id: "ROUTE-07", latest_task_id: "TASK-LIVE-13", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "司机十三上报车辆故障", status: "PENDING", reported_at: "2026-09-16T10:00:00Z" },
        { row_id: 2, anomaly_no: "ANOM-ROAD", order_no: "ORD-15", driver_id: "D-008", vehicle_id: "V-008", route_id: "R-1", latest_task_id: "TASK-ROAD", anomaly_type: "ROAD_BLOCKED", risk: "HIGH", description: "东河桥段堵塞", status: "COMPLETED", reported_at: "2026-09-09T09:28:45Z" },
        { row_id: 1, anomaly_no: "ANOM-FAULT", order_no: "ORD-16", driver_id: "D-001", vehicle_id: "V-001", route_id: "R-2", latest_task_id: "TASK-FAULT", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "车辆无法行驶", status: "COMPLETED", reported_at: "2026-09-09T09:20:00Z" },
      ], total: 4, next_cursor: null, provenance: "LIVE",
    });
    taskApi.getTaskStatus.mockImplementation(async (taskId: string) => ({ task_id: taskId, order_id: 14, status: "RUNNING", started_at: now, completed_at: null, created_at: now, ready: true, requires_manual_review: false }));
    taskApi.getTaskResult.mockImplementation(async (taskId: string) => ({
      ...resultByTask["TASK-FAULT"],
      task_id: taskId,
      status: "RUNNING",
      vehicle_allocation: { ...resultByTask["TASK-FAULT"].vehicle_allocation, original_vehicle_id: taskId === "TASK-LIVE-14" ? "V-014" : "V-013", target_vehicle_id: "V-015" },
      dispatch_impact: { ...resultByTask["TASK-FAULT"].dispatch_impact, incident_vehicle_id: taskId === "TASK-LIVE-14" ? "V-014" : "V-013", replacement_vehicle_id: "V-015" },
    }));

    const refresh = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent?.includes("刷新"));
    await act(async () => { refresh?.click(); });
    await flush();
    await flush();
    expect(view.container.querySelector("[data-live-driver-report]")?.textContent).toContain("D-014");
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]')?.value).toBe("TASK-LIVE-14");

    await act(async () => { view.container.querySelector<HTMLButtonElement>('button[aria-label="关闭司机上报提醒"]')?.click(); });
    await flush();
    await flush();
    expect(view.container.querySelector("[data-live-driver-report]")?.textContent).toContain("D-013");
    expect(view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]')?.value).toBe("TASK-LIVE-13");
    expect(view.container.querySelector('[data-fleet-vehicle-detail="V-013"]')).not.toBeNull();
    await act(async () => { view.root.unmount(); });
  });

  it("loads the rescue snapshot for legacy lowercase breakdown types", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [
        { row_id: 4, anomaly_no: "DEMO-ANOM-004", order_no: "DEMO-ORDER-004", driver_id: "D-001", vehicle_id: "V-001", route_id: "ROUTE-01", latest_task_id: "TASK-FAULT", anomaly_type: "vehicle_breakdown", risk: "HIGH", description: "车辆发动机告警", status: "OPEN", reported_at: "2026-09-09T09:20:00Z" },
      ], total: 1, next_cursor: null, provenance: "DEMO",
    });
    taskApi.getTaskResult.mockResolvedValue({
      ...resultByTask["TASK-FAULT"],
      anomaly_type: "vehicle_breakdown",
    });

    const view = await renderPage();
    await flush();
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
    await flush();

    expect(operationApi.getMapSnapshot).toHaveBeenCalledWith("TASK-FAULT");
    await act(async () => { view.root.unmount(); });
  });

  it("renders the twenty-vehicle sandbox, ten named routes, and Chinese task identifiers", async () => {
    const view = await renderPage();
    await flush();

    const selector = view.container.querySelector<HTMLSelectElement>('select[aria-label="选择地图任务"]');
    expect(selector).not.toBeNull();
    expect(selector?.value).toBe("TASK-ROAD");
    expect(selector?.selectedOptions[0]?.textContent).toBe("异常-002｜运单-015｜道路堵塞-02｜调度完成-03｜调度任务-002");
    expect(selector?.selectedOptions[0]?.textContent).not.toContain("ROAD_BLOCKED");
    expect(view.container.textContent).not.toContain("TASK-ROAD");
    expect(view.container.textContent).toContain("20 辆车辆实时态势");
    expect(view.container.querySelectorAll("[data-fleet-kpi]")).toHaveLength(4);
    expect(view.container.querySelector('[data-fleet-kpi="online"]')?.textContent).toContain("在线车辆");
    expect(view.container.querySelector('[data-fleet-kpi="transit"]')?.textContent).toContain("运输中");
    expect(view.container.querySelector('[data-fleet-kpi="abnormal"]')?.textContent).toContain("异常车辆");
    expect(view.container.querySelector('[data-fleet-kpi="alerts"]')?.textContent).toContain("今日告警");
    expect(view.container.querySelector('[data-provenance="LIVE"]')?.textContent).toContain("实时业务数据");
    expect(view.container.textContent).toContain("后端异常任务与车辆处置快照");
    expect(view.container.textContent).toContain("虚拟沙盘实时模拟，不采集真实 GPS");
    expect(view.container.querySelectorAll("[data-fleet-vehicle-id]")).toHaveLength(20);
    expect(view.container.querySelectorAll('select[aria-label="选择高亮路线"] option[data-route-id]')).toHaveLength(10);
    expect(view.container.querySelectorAll("[data-fleet-stop-id]")).toHaveLength(22);
    expect(view.container.querySelectorAll("[data-fleet-route-label]")).toHaveLength(10);
    expect(view.container.querySelectorAll("[data-road-name]").length).toBeGreaterThanOrEqual(6);
    expect(view.container.querySelectorAll("[data-road-shield]").length).toBeGreaterThanOrEqual(3);
    expect(view.container.textContent).toContain("路线-01 · 调度中心—快递集散线");
    expect(view.container.textContent).toContain("智慧物流调度中心");
    expect(view.container.textContent).toContain("快递集散站");
    expect(view.container.textContent).toContain("路线-10 · 维修救援接驳线");
    expect(view.container.querySelector(".fleet-sandbox-canvas")).not.toBeNull();
    expect(view.container.querySelector('button[aria-label="切换卫星地图"]')).not.toBeNull();
    expect(view.container.querySelector('button[aria-label="切换夜间地图"]')?.classList.contains("is-active")).toBe(true);
    expect(view.container.querySelector('button[aria-label="放大全景地图"]')).not.toBeNull();
    expect(view.container.querySelector('button[aria-label="缩小全景地图"]')).not.toBeNull();
    expect(view.container.querySelector('button[aria-label="复位全景地图"]')).not.toBeNull();
    const followButton = view.container.querySelector<HTMLButtonElement>('button[aria-label="跟随选中车辆"]');
    expect(followButton?.getAttribute("aria-pressed")).toBe("false");
    await act(async () => { followButton?.click(); });
    expect(view.container.querySelector('button[aria-label="停止跟随车辆"]')?.getAttribute("aria-pressed")).toBe("true");
    expect(view.container.querySelector('button[aria-label="全屏查看地图"]')).not.toBeNull();
    const fullscreenButton = view.container.querySelector<HTMLButtonElement>('button[aria-label="全屏查看地图"]');
    await act(async () => { fullscreenButton?.click(); });
    expect(view.container.querySelector(".fleet-sandbox-map-shell")?.classList.contains("is-fullscreen")).toBe(true);
    await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); });
    expect(view.container.querySelector(".fleet-sandbox-map-shell")?.classList.contains("is-fullscreen")).toBe(false);
    expect(view.container.querySelector(".fleet-sandbox-canvas")?.getAttribute("data-map-mode")).toBe("STANDARD");
    expect(view.container.querySelector(".fleet-sandbox-canvas")?.getAttribute("data-interactive")).toBe("true");
    expect(view.container.querySelector(".fleet-road-casings path")).not.toBeNull();
    expect(view.container.querySelector(".fleet-road-casings path")?.getAttribute("d")).toContain("Q");
    expect(view.container.querySelector(".fleet-map-terrain-satellite")).not.toBeNull();
    expect(view.container.querySelector('image.fleet-map-aerial-image')?.getAttribute("href")).toBe("/assets/maps/xinping-satellite.webp");
    expect(view.container.querySelector(".fleet-map-attribution")?.textContent).toContain("影像");
    expect(view.container.querySelector(".fleet-map-headbar")).not.toBeNull();
    expect(view.container.querySelector('[aria-label="地图图层与车辆状态"]')).not.toBeNull();
    const mobileLayerToggle = view.container.querySelector<HTMLButtonElement>('button[aria-label="展开地图图层"]');
    expect(mobileLayerToggle?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => { mobileLayerToggle?.click(); });
    expect(view.container.querySelector('button[aria-label="收起地图图层"]')?.getAttribute("aria-expanded")).toBe("true");
    const historyMode = Array.from(view.container.querySelectorAll<HTMLButtonElement>(".fleet-map-command-tabs button")).find((button) => button.textContent?.includes("历史轨迹"));
    await act(async () => { historyMode?.click(); });
    expect(historyMode?.classList.contains("is-active")).toBe(true);
    const geofenceMode = Array.from(view.container.querySelectorAll<HTMLButtonElement>(".fleet-map-command-tabs button")).find((button) => button.textContent?.includes("电子围栏"));
    await act(async () => { geofenceMode?.click(); });
    expect(geofenceMode?.classList.contains("is-active")).toBe(true);
    const trafficLayer = view.container.querySelector<HTMLButtonElement>('button[aria-label="切换交通路况"]');
    await act(async () => { trafficLayer?.click(); });
    expect(trafficLayer?.classList.contains("is-active")).toBe(true);
    expect(view.container.querySelector(".fleet-map-alert-card")).not.toBeNull();
    expect(view.container.querySelector(".fleet-stat-donut")).not.toBeNull();
    expect(view.container.querySelector(".fleet-mileage-ranking")).not.toBeNull();
    expect(view.container.querySelectorAll("[data-fleet-footer-metric]")).toHaveLength(4);
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-01"]')?.getAttribute("role")).toBe("button");
    expect(view.container.querySelector('[data-fleet-edge-id="E04"].is-blocked')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-02"][data-dispatch-state="REROUTED"]')).not.toBeNull();

    await act(async () => {
      if (!selector) return;
      selector.value = "TASK-FAULT";
      selector.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
    await flush();

    expect(selector?.selectedOptions[0]?.textContent).toBe("异常-001｜运单-016｜车辆故障-01｜调度完成-03｜调度任务-001");
    expect(view.container.querySelector("[data-operation-lifecycle]")).not.toBeNull();
    const dispatcherTimeline = view.container.querySelector('[data-vehicle-operation-timeline][data-context="dispatcher"]');
    expect(dispatcherTimeline).not.toBeNull();
    expect(dispatcherTimeline?.querySelectorAll("[data-operation-stage]")).toHaveLength(4);
    expect(dispatcherTimeline?.textContent).toContain("发现故障");
    expect(dispatcherTimeline?.textContent).toContain("预计自动复岗");
    expect(view.container.querySelectorAll("[data-operation-map-route]")).toHaveLength(3);
    expect(view.container.textContent).toContain("下一站");
    expect(view.container.textContent).toContain("预计到达");
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-001"][data-fleet-status="BROKEN"]')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-005"][data-fleet-status="IN_TRANSIT"]')).not.toBeNull();
    expect(view.container.textContent).toContain("故障车辆 V-001");
    expect(view.container.textContent).toContain("已派出替代车辆 V-005");
    expect(view.container.querySelector('[data-dispatch-impact="CALCULATED"]')).toBeNull();
    const incidentVehicle = view.container.querySelector<SVGGElement>('[data-fleet-vehicle-id="V-001"]');
    await act(async () => { incidentVehicle?.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    const dispatchImpact = view.container.querySelector('[data-dispatch-impact="CALCULATED"]');
    expect(dispatchImpact).not.toBeNull();
    expect(dispatchImpact?.querySelector('[data-impact-role="incident"]')?.textContent).toContain("V-001");
    expect(dispatchImpact?.querySelector('[data-impact-role="replacement"]')?.textContent).toContain("V-005");
    expect(dispatchImpact?.querySelector('[data-impact-metric="pickup"]')?.textContent).toContain("+2.80 km");
    expect(dispatchImpact?.querySelector('[data-impact-metric="pickup"]')?.textContent).toContain("+6 分钟");
    expect(dispatchImpact?.querySelector('[data-impact-metric="route"]')?.textContent).toContain("+3.20 km");
    expect(dispatchImpact?.querySelector('[data-impact-metric="route"]')?.textContent).toContain("+4 分钟");
    expect(dispatchImpact?.querySelector('[data-impact-metric="total"]')?.textContent).toContain("+6.00 km");
    expect(dispatchImpact?.querySelector('[data-impact-metric="total"]')?.textContent).toContain("预计晚到 10 分钟");
    const routineVehicle = view.container.querySelector<SVGGElement>('[data-fleet-vehicle-id="V-002"]');
    await act(async () => { routineVehicle?.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    const routineVehicleDetail = view.container.querySelector('[data-fleet-vehicle-detail="V-002"]');
    expect(routineVehicleDetail).not.toBeNull();
    expect(routineVehicleDetail?.textContent).toContain("车辆运行详情");
    expect(routineVehicleDetail?.textContent).toContain("V-002");
    expect(routineVehicleDetail?.textContent).toContain("路线-01 · 调度中心—快递集散线");
    expect(routineVehicleDetail?.textContent).toContain("行驶中");
    expect(routineVehicleDetail?.querySelector('[data-impact-metric="total"]')).toBeNull();
    expect(view.container.querySelector('[data-dispatch-impact="CALCULATED"]')).toBeNull();
    const replacementVehicle = view.container.querySelector<SVGGElement>('[data-fleet-vehicle-id="V-005"]');
    await act(async () => { replacementVehicle?.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(view.container.querySelector('[data-fleet-vehicle-detail="V-005"]')).not.toBeNull();
    expect(view.container.querySelector('[data-dispatch-impact="CALCULATED"]')).not.toBeNull();
    const closeImpact = view.container.querySelector<HTMLButtonElement>('button[aria-label="关闭车辆运行详情"]');
    await act(async () => { closeImpact?.click(); });
    expect(view.container.querySelector('[data-dispatch-impact="CALCULATED"]')).toBeNull();
    expect(view.container.querySelector("[data-fleet-vehicle-detail]")).toBeNull();
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-10"][data-dispatch-state="RESCUE"]')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-10"][data-map-priority="critical"]')).not.toBeNull();
    expect(view.container.querySelectorAll('[data-fleet-route-id][data-map-priority="background"].is-visible').length).toBeGreaterThanOrEqual(8);
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-001"][data-map-priority="critical"]')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-005"][data-map-priority="critical"]')).not.toBeNull();
    await act(async () => { view.root.unmount(); });
  });

  it("keeps vehicle centers on their routes and advances them in small continuous steps", async () => {
    vi.useFakeTimers();
    const view = await renderPage();
    await flush();

    const marker = view.container.querySelector<SVGGElement>('[data-fleet-vehicle-id="V-002"]');
    expect(marker).not.toBeNull();
    expect(marker?.getAttribute("data-route-offset")).toBe("0");
    expect(marker?.hasAttribute("data-overlap-offset")).toBe(false);
    const before = marker?.getAttribute("transform") ?? "";

    await act(async () => { vi.advanceTimersByTime(1500); });
    const after = marker?.getAttribute("transform") ?? "";
    const readPoint = (value: string) => value.match(/translate\(([-\d.]+) ([-\d.]+)\)/)?.slice(1).map(Number) ?? [];
    const [beforeX, beforeY] = readPoint(before);
    const [afterX, afterY] = readPoint(after);
    const distance = Math.hypot(afterX - beforeX, afterY - beforeY);

    expect(after).not.toBe(before);
    expect(distance).toBeGreaterThan(0);
    expect(distance).toBeLessThan(20);
    await act(async () => { view.root.unmount(); });
  });

  it("opens a matching vehicle detail card from every fleet roster item", async () => {
    const view = await renderPage();
    await flush();

    expect(view.container.querySelector("[data-fleet-vehicle-detail]")).toBeNull();
    const rosterItems = Array.from(view.container.querySelectorAll<HTMLButtonElement>("[data-fleet-roster-id]"));
    expect(rosterItems).toHaveLength(20);

    for (const item of rosterItems) {
      const vehicleId = item.dataset.fleetRosterId;
      await act(async () => { item.click(); });
      expect(view.container.querySelector(`[data-fleet-vehicle-detail="${vehicleId}"]`)).not.toBeNull();
    }

    await act(async () => { view.root.unmount(); });
  });

  it("zooms to the selected route and removes unrelated routes, stops, and vehicles", async () => {
    const view = await renderPage();
    await flush();

    expect(view.container.querySelector(".fleet-selected-vehicle h3")?.textContent).toBe("V-008");

    const routeSelector = view.container.querySelector<HTMLSelectElement>('select[aria-label="选择高亮路线"]');
    await act(async () => {
      if (!routeSelector) return;
      routeSelector.value = "ROUTE-02";
      routeSelector.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const map = view.container.querySelector<SVGElement>('.fleet-sandbox-canvas[data-map-focus="ROUTE-02"]');
    expect(map).not.toBeNull();
    expect(map?.getAttribute("viewBox")).not.toBe("0 0 1200 680");
    expect(map?.querySelectorAll("[data-fleet-route-id]")).toHaveLength(1);
    expect(map?.querySelector('[data-fleet-route-id="ROUTE-02"]')).not.toBeNull();
    expect(map?.querySelector('[data-fleet-route-id="ROUTE-01"]')).toBeNull();
    expect(map?.querySelectorAll("[data-fleet-stop-id]")).toHaveLength(8);
    expect(map?.querySelector('[data-fleet-stop-id="N08"]')).not.toBeNull();
    expect(map?.querySelector('[data-fleet-stop-id="N11"]')).toBeNull();
    expect(map?.querySelector('[data-fleet-vehicle-id="V-002"]')).toBeNull();
    expect(map?.querySelector('[data-fleet-vehicle-id="V-003"]')).not.toBeNull();
    await act(async () => { view.root.unmount(); });
  });

  it("polls for new reports and marks the reported vehicle before AI allocation is ready", async () => {
    vi.useFakeTimers();
    workspaceReadApi.getAnomalies.mockResolvedValue({
      items: [{ row_id: 3, anomaly_no: "ANOM-PENDING", order_no: "ORD-21", driver_id: "D-001", vehicle_id: "V-001", route_id: "R-1", latest_task_id: "TASK-PENDING", anomaly_type: "VEHICLE_BREAKDOWN", risk: "HIGH", description: "司机上报车辆故障", status: "REPORTED", reported_at: "2026-09-09T10:00:00Z" }],
      total: 1, next_cursor: null, provenance: "LIVE",
    });
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-PENDING", order_id: 21, status: "PENDING", started_at: null, completed_at: null, created_at: "2026-09-09T10:00:00Z", ready: false, requires_manual_review: false });
    const view = await renderPage();
    await flush();

    expect(view.container.querySelector('[data-fleet-vehicle-id="V-001"][data-fleet-status="BROKEN"]')).not.toBeNull();
    expect(view.container.textContent).toContain("异常已上报");
    const initialCalls = workspaceReadApi.getAnomalies.mock.calls.length;

    await act(async () => { vi.advanceTimersByTime(3000); });
    await flush();
    expect(workspaceReadApi.getAnomalies.mock.calls.length).toBeGreaterThan(initialCalls);
    await act(async () => { view.root.unmount(); });
  });

  it("keeps the rendered map visible while a background poll is pending", async () => {
    vi.useFakeTimers();
    const firstPage = await workspaceReadApi.getAnomalies();
    const backgroundRefresh = deferred<typeof firstPage>();
    workspaceReadApi.getAnomalies
      .mockResolvedValueOnce(firstPage)
      .mockReturnValueOnce(backgroundRefresh.promise);
    const view = await renderPage();
    await flush();

    expect(view.container.querySelector(".fleet-sandbox-canvas")).not.toBeNull();

    await act(async () => { vi.advanceTimersByTime(3000); });
    await flush();

    expect(view.container.querySelector(".fleet-sandbox-canvas")).not.toBeNull();
    expect(view.container.textContent).not.toContain("正在读取最近异常任务");

    await act(async () => { backgroundRefresh.resolve(firstPage); });
    await flush();
    await act(async () => { view.root.unmount(); });
  });
});
