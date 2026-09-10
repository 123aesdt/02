import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const workspaceReadApi = vi.hoisted(() => ({ getAnomalies: vi.fn() }));
const taskApi = vi.hoisted(() => ({ getTaskStatus: vi.fn(), getTaskResult: vi.fn() }));
const ticketApi = vi.hoisted(() => ({ issueTaskWsTicket: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));
vi.mock("../src/services/dispatch-service", () => taskApi);
vi.mock("../src/services/api/ws-ticket-client", () => ticketApi);

import { setAuthenticatedSession, clearSession } from "../src/auth/session";
import { FleetLiveMapPage } from "../src/pages/fleet-live-map-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
  ticketApi.issueTaskWsTicket.mockResolvedValue("ticket");
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
  clearSession();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("administrator fleet live map page", () => {
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
    expect(view.container.textContent).toContain("虚拟沙盘实时模拟，不采集真实 GPS");
    expect(view.container.querySelectorAll("[data-fleet-vehicle-id]")).toHaveLength(20);
    expect(view.container.querySelectorAll('select[aria-label="选择高亮路线"] option[data-route-id]')).toHaveLength(10);
    expect(view.container.querySelectorAll("[data-fleet-stop-id]")).toHaveLength(18);
    expect(view.container.querySelectorAll("[data-fleet-route-label]")).toHaveLength(10);
    expect(view.container.querySelectorAll("[data-road-name]").length).toBeGreaterThanOrEqual(6);
    expect(view.container.textContent).toContain("路线-01 · 中心仓—城东配送线");
    expect(view.container.textContent).toContain("路线-10 · 维修救援接驳线");
    expect(view.container.querySelector(".fleet-sandbox-canvas")).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-edge-id="E04"].is-blocked')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-02"][data-dispatch-state="REROUTED"]')).not.toBeNull();

    await act(async () => {
      if (!selector) return;
      selector.value = "TASK-FAULT";
      selector.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();

    expect(selector?.selectedOptions[0]?.textContent).toBe("异常-001｜运单-016｜车辆故障-01｜调度完成-03｜调度任务-001");
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-001"][data-fleet-status="BROKEN"]')).not.toBeNull();
    expect(view.container.querySelector('[data-fleet-vehicle-id="V-005"][data-fleet-status="DISPATCHING"]')).not.toBeNull();
    expect(view.container.textContent).toContain("故障车辆 V-001");
    expect(view.container.textContent).toContain("已派出替代车辆 V-005");
    expect(view.container.querySelector('[data-fleet-route-id="ROUTE-10"][data-dispatch-state="RESCUE"]')).not.toBeNull();
    await act(async () => { view.root.unmount(); });
  });

  it("keeps vehicle centers on their routes and advances them in small continuous steps", async () => {
    vi.useFakeTimers();
    const view = await renderPage();
    await flush();

    const marker = view.container.querySelector<SVGGElement>('[data-fleet-vehicle-id="V-002"]');
    expect(marker).not.toBeNull();
    expect(marker?.getAttribute("data-route-offset")).toBe("0");
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
    expect(map?.querySelectorAll("[data-fleet-stop-id]")).toHaveLength(6);
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
});
