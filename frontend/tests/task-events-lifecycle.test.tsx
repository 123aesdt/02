import { act, useCallback, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const testRuntime = vi.hoisted(() => ({ dataMode: "mock" as "mock" | "api" }));
const taskApi = vi.hoisted(() => ({
  getTaskStatus: vi.fn(),
  getTaskResult: vi.fn(),
  publishDispatchTask: vi.fn(),
}));
const ticketApi = vi.hoisted(() => ({ issueTaskWsTicket: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    get dataMode() { return testRuntime.dataMode; },
    apiBaseUrl: "http://api.test",
  },
}));
vi.mock("../src/services/dispatch-service", () => taskApi);
vi.mock("../src/services/api/ws-ticket-client", () => ticketApi);

import { ApiDispatchDetailPage } from "../src/pages/api-dispatch-detail-page";
import { useTaskEvents } from "../src/hooks/use-task-events";
import type { TaskEvent } from "../src/types/task-events";
import { clearSession, setAuthenticatedSession } from "../src/auth/session";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close = vi.fn(() => this.emitClose(1000));

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  emitMessage(event: TaskEvent): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent);
  }

  emitClose(code: number): void {
    this.onclose?.({ code } as CloseEvent);
  }
}

function event(taskId: string, eventId: string, sequence: number): TaskEvent {
  return {
    event_id: eventId,
    task_id: taskId,
    event_type: "INTAKE_COMPLETED",
    node: "intake",
    status: "PROCESSING",
    timestamp: "2026-08-22T00:00:00Z",
    sequence,
    data: {},
  };
}

function EventsProbe({ taskId, onUpdate }: { taskId: string; onUpdate: (events: TaskEvent[]) => void }) {
  const onTerminal = useCallback(() => undefined, []);
  const { events } = useTaskEvents(taskId, onTerminal);
  useEffect(() => onUpdate(events), [events, onUpdate]);
  return null;
}

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  return { root, container };
}

async function flush(): Promise<void> {
  await act(async () => { await Promise.resolve(); });
}

afterEach(async () => {
  testRuntime.dataMode = "mock";
  taskApi.getTaskStatus.mockReset();
  taskApi.getTaskResult.mockReset();
  taskApi.publishDispatchTask.mockReset();
  ticketApi.issueTaskWsTicket.mockReset();
  clearSession();
  FakeWebSocket.instances = [];
  vi.unstubAllGlobals();
  vi.useRealTimers();
  document.body.replaceChildren();
});

beforeEach(() => {
  ticketApi.issueTaskWsTicket.mockResolvedValue("test-ws-ticket");
  setAuthenticatedSession("test-token", {
    subject_id: "test-admin", display_name: "Test Admin", roles: ["ADMIN"], permissions: ["dispatch:read"],
    auth_method: "development_jwt", issued_at: "2026-08-28T00:00:00Z", expires_at: "2099-08-28T01:00:00Z",
  });
});

describe("Task event lifecycle", () => {
  it("closes the old task socket and prevents its events from reaching the replacement task", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const updates: TaskEvent[][] = [];
    const { root } = await render(<EventsProbe taskId="TASK-1" onUpdate={(events) => { updates.push(events); }} />);
    const oldSocket = FakeWebSocket.instances[0];

    await act(async () => { root.render(<EventsProbe taskId="TASK-2" onUpdate={(events) => { updates.push(events); }} />); });
    expect(oldSocket.close).toHaveBeenCalledOnce();
    await act(async () => { oldSocket.emitMessage(event("TASK-2", "stale-event", 1)); });
    expect(updates.at(-1)).toEqual([]);

    await act(async () => { FakeWebSocket.instances[1].emitMessage(event("TASK-2", "current-event", 1)); });
    expect(updates.at(-1)?.map((item) => item.event_id)).toEqual(["current-event"]);
    await act(async () => { root.unmount(); });
  });

  it("closes an active socket on unmount", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const { root } = await render(<EventsProbe taskId="TASK-1" onUpdate={() => undefined} />);
    const socket = FakeWebSocket.instances[0];
    await act(async () => { root.unmount(); });
    expect(socket.close).toHaveBeenCalledOnce();
  });

  it("disables a scheduled reconnect when the component unmounts", async () => {
    testRuntime.dataMode = "api";
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const { root } = await render(<EventsProbe taskId="TASK-1" onUpdate={() => undefined} />);
    const socket = FakeWebSocket.instances[0];
    await act(async () => { socket.emitClose(1006); });
    await act(async () => { root.unmount(); });
    await act(async () => { vi.advanceTimersByTime(8000); });
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("keeps mock mode on its playback path without creating a WebSocket", async () => {
    testRuntime.dataMode = "mock";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const updates: TaskEvent[][] = [];
    const { root } = await render(<EventsProbe taskId="TASK-1" onUpdate={(events) => { updates.push(events); }} />);
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(updates.at(-1)).toEqual([]);
    await act(async () => { root.unmount(); });
  });

  it("creates a task socket only in API mode and refetches status and result once for a terminal event", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "COMPLETED", started_at: null, completed_at: null, created_at: "2026-08-22T00:00:00Z", ready: true, requires_manual_review: false });
    taskApi.getTaskResult.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "COMPLETED", ready: true, dispatch: null, audit: null });
    const { root } = await render(<ApiDispatchDetailPage taskId="TASK-1" />);
    await flush();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(taskApi.getTaskStatus).toHaveBeenCalledOnce();
    expect(taskApi.getTaskResult).toHaveBeenCalledOnce();

    const terminal: TaskEvent = { ...event("TASK-1", "terminal", 1), event_type: "TASK_COMPLETED", node: "audit", status: "COMPLETED" };
    await act(async () => {
      FakeWebSocket.instances[0].emitMessage(terminal);
      FakeWebSocket.instances[0].emitMessage(terminal);
    });
    expect(taskApi.getTaskStatus).toHaveBeenCalledTimes(2);
    expect(taskApi.getTaskResult).toHaveBeenCalledTimes(2);
    await act(async () => { root.unmount(); });
  });

  it("shows the eight-agent graph stage and event-sourced graph evidence", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "PROCESSING", started_at: null, completed_at: null, created_at: "2026-08-22T00:00:00Z", ready: false, requires_manual_review: false });
    taskApi.getTaskResult.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "PROCESSING", ready: false, dispatch: null, audit: null });
    const { root, container } = await render(<ApiDispatchDetailPage taskId="TASK-1" />);
    await flush();

    const graphEvent: TaskEvent = {
      ...event("TASK-1", "graph-complete", 3),
      event_type: "GRAPH_MEMORY_COMPLETED",
      node: "graph_memory",
      data: {
        graph_memory_used: true,
        graph_memory_facts: [{ source: { display_name: "李师傅" }, relation_type: "HAS_RISK_ON", target: { display_name: "新平路" } }],
        graph_memory_paths: [{ entities: [{ display_name: "李师傅" }, { display_name: "新平路" }] }],
      },
    };
    await act(async () => { FakeWebSocket.instances[0].emitMessage(graphEvent); });

    expect(container.querySelectorAll(".pipeline-item")).toHaveLength(8);
    expect(container.textContent).toContain("图记忆智能体");
    expect(container.textContent).toContain("李师傅 → 存在风险 → 新平路");
    await act(async () => { root.unmount(); });
  });

  it("restores fleet replacement evidence without mislabeling paired route evidence as a road blockage", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    setAuthenticatedSession("review-token", {
      subject_id: "test-supervisor", display_name: "调度主管", roles: ["SUPERVISOR"], permissions: ["dispatch:read", "dispatch:review"],
      auth_method: "development_jwt", issued_at: "2026-08-28T00:00:00Z", expires_at: "2099-08-28T01:00:00Z",
    });
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "COMPLETED", started_at: null, completed_at: "2026-09-07T10:00:00Z", created_at: "2026-09-07T09:59:00Z", ready: true, requires_manual_review: false });
    taskApi.getTaskResult.mockResolvedValue({
      task_id: "TASK-1", order_id: 128, status: "COMPLETED", ready: true, anomaly_type: "VEHICLE_BREAKDOWN", dispatch: null, audit: null,
      vehicle_allocation: {
        original_vehicle_id: "V-001", target_vehicle_id: "V-005", target_driver_id: "D-003", vehicle_reassigned: true, scoring_formula: "FLEET_SCORE_V1",
        pickup_route: { objective: "FASTEST", node_ids: ["N15", "N04"], edge_ids: ["E20"], distance_km: "2.80", estimated_minutes: 6, risk_cost: "0.10", visited_node_count: 2, scoring_formula: null },
        candidate_vehicles: [
          { vehicle_id: "V-001", driver_id: "D-001", vehicle_status: "BROKEN", driver_status: "ON_DUTY", remaining_capacity_kg: "800.00", gross_weight_tons: "2.80", cargo_capability: "COLD_CHAIN", pickup_route: null, pickup_distance_km: null, pickup_eta_minutes: null, score: null, score_components: null, scoring_formula: null, eligible: false, exclusion_reasons: ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"] },
          { vehicle_id: "V-005", driver_id: "D-003", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY", remaining_capacity_kg: "900.00", gross_weight_tons: "2.40", cargo_capability: "COLD_CHAIN", pickup_route: null, pickup_distance_km: "2.80", pickup_eta_minutes: 6, score: "93.4", score_components: null, scoring_formula: "FLEET_SCORE_V1", eligible: true, exclusion_reasons: [] },
        ],
      },
      route_plan: {
        original_path: { objective: "FASTEST", node_ids: ["N01", "N02"], edge_ids: ["E04"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "1.00", visited_node_count: 4, scoring_formula: null },
        recommended_path: { objective: "FASTEST", node_ids: ["N01", "N03", "N02"], edge_ids: ["E07", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0.30", visited_node_count: 8, scoring_formula: "ROUTE_SCORE_V1" },
        candidate_routes: [], blocked_edge_ids: ["E04"], distance_delta_km: "3.20", eta_delta_minutes: 4, visited_node_count: 8, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 7,
        network_nodes: [{ node_id: "N01", name: "中心仓", x_km: "0.00", y_km: "0.00", node_type: "DEPOT" }, { node_id: "N02", name: "城东站", x_km: "4.00", y_km: "0.00", node_type: "STATION" }, { node_id: "N03", name: "北环口", x_km: "2.00", y_km: "2.00", node_type: "JUNCTION" }],
        network_edges: [
          { edge_id: "E04", name: "新平路东河桥段", from_node_id: "N01", to_node_id: "N02", distance_km: "10.00", base_minutes: 20, road_level: "COUNTY", risk_level: "HIGH", status: "BLOCKED", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
          { edge_id: "E07", name: "北环支路", from_node_id: "N01", to_node_id: "N03", distance_km: "6.20", base_minutes: 11, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
          { edge_id: "E09", name: "城东联络线", from_node_id: "N03", to_node_id: "N02", distance_km: "7.00", base_minutes: 13, road_level: "COUNTY", risk_level: "LOW", status: "OPEN", congestion_factor: "1.00", weight_limit_tons: "6.00", bidirectional: true, version: 7 },
        ],
      },
    });

    const { root, container } = await render(<ApiDispatchDetailPage taskId="TASK-1" />);
    await flush();

    expect(container.getElementsByClassName("dispatch-evidence-overview")).toHaveLength(1);
    expect(container.textContent).toContain("异常处置结果总览");
    expect(container.textContent).toContain("V-001 车辆故障");
    expect(container.textContent).toContain("比较 2 辆候选车辆");
    expect(container.textContent).toContain("V-005 接替");
    expect(container.textContent).toContain("评分 93.4");
    expect(container.querySelector(".dispatch-evidence-overview")?.textContent).not.toContain("E04 道路堵塞");
    expect(container.querySelector('.dispatch-evidence-overview a[href="#fleet-allocation-title"]')?.textContent).toContain("查看车辆计算依据");
    expect(container.querySelector('nav[aria-label="答辩讲解导航"] a[href="#agent-pipeline-title"]')?.textContent).toContain("Agent 流水线");
    expect(container.querySelector("#agent-pipeline-title")?.textContent).toBe("智能体流水线");
    expect(container.querySelector('.dispatch-evidence-overview a[href="#route-plan-result-title"]')).toBeNull();
    expect(container.textContent).toContain("替代车辆调度计算");
    expect(container.textContent).toContain("接驳 2.80 公里 · 6 分钟");
    expect(container.querySelector(".live-vehicle-map")).not.toBeNull();
    expect(container.textContent).toContain("车辆实时调度地图");
    expect(container.textContent).toContain("虚拟沙盘实时模拟");
    expect(container.textContent).toContain("V-001 · 故障车辆");
    expect(container.textContent).toContain("V-005 · 已派出");
    expect(container.textContent).not.toContain("新路线规划计算");
    expect(container.querySelector(".route-plan-result-panel")).toBeNull();
    expect(container.querySelectorAll(".pipeline-item")).toHaveLength(8);
    await act(async () => { root.unmount(); });
  });

  it("lets a reviewer publish an approved route and shows the durable publication receipt", async () => {
    testRuntime.dataMode = "api";
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    setAuthenticatedSession("review-token", {
      subject_id: "test-supervisor", display_name: "调度主管", roles: ["SUPERVISOR"], permissions: ["dispatch:read", "dispatch:review"],
      auth_method: "development_jwt", issued_at: "2026-08-28T00:00:00Z", expires_at: "2099-08-28T01:00:00Z",
    });
    taskApi.getTaskStatus.mockResolvedValue({ task_id: "TASK-1", order_id: 128, status: "COMPLETED", started_at: null, completed_at: "2026-08-30T11:03:04Z", created_at: "2026-08-30T11:00:00Z", ready: true, requires_manual_review: false });
    taskApi.getTaskResult.mockResolvedValue({
      task_id: "TASK-1", order_id: 128, status: "COMPLETED", ready: true,
      dispatch: { dispatch_id: 1, dispatch_no: "DSP-1", original_route_id: "xinping-road", target_route_id: "national-102", status: "REROUTED", decision_reason: "更加安全", fallback_used: false, fallback_reason: null, version: 1, executed: true },
      audit: { result: "APPROVED", reason: "审核通过", dispatch_id: 1, created_at: "2026-08-30T11:03:04Z" },
      publication: { status: "PENDING", route_id: null, route_instruction: null, published_at: null, published_by: null, recipient_employee_id: "CF-DEMO-001", recipient_display_name: "张调度" },
    });
    taskApi.publishDispatchTask.mockResolvedValue({
      task_id: "TASK-1", dispatch_id: 1, status: "PUBLISHED", route_id: "national-102",
      route_instruction: "从青云镇出发，按 national-102 行驶，前往临港镇。途中注意现场路况并服从安全调度。",
      published_at: "2026-08-30T12:00:00Z", published_by: "调度主管",
      recipient_employee_id: "CF-DEMO-001", recipient_display_name: "张调度", duplicate: false,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const { root, container } = await render(<ApiDispatchDetailPage taskId="TASK-1" />);
    await flush();
    const publishButton = [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent?.includes("发布调度单"));
    expect(publishButton).toBeTruthy();

    await act(async () => { publishButton?.click(); });
    await flush();

    expect(taskApi.publishDispatchTask).toHaveBeenCalledWith("TASK-1");
    expect(container.textContent).toContain("已发布");
    expect(container.textContent).toContain("调度主管");
    expect(container.textContent).toContain("接收员工");
    expect(container.textContent).toContain("张调度");
    expect(container.textContent).toContain("从青云镇出发");
    await act(async () => { root.unmount(); });
  });
});
