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
