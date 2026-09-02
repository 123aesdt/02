import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskEventClient, toTaskEventWebSocketUrl } from "../src/services/task-event-client";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  close = vi.fn(() => this.emitClose(1000));

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  emitOpen(): void {
    this.onopen?.(new Event("open"));
  }

  emitClose(code: number): void {
    this.onclose?.({ code } as CloseEvent);
  }
}

afterEach(() => {
  FakeWebSocket.instances = [];
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Task event WebSocket client", () => {
  it("builds ws and wss URLs from the configured API base URL", () => {
    expect(toTaskEventWebSocketUrl("http://127.0.0.1:8000", "TASK-1", "ticket-1")).toBe("ws://127.0.0.1:8000/api/v1/ws/tasks/TASK-1?ticket=ticket-1");
    expect(toTaskEventWebSocketUrl("https://api.example", "TASK-1", "ticket-1", "evt-1")).toBe("wss://api.example/api/v1/ws/tasks/TASK-1?ticket=ticket-1&last_event_id=evt-1");
  });

  it("deduplicates event ids and retains the latest event id for reconnect", () => {
    const received: string[] = [];
    const client = new TaskEventClient("http://api.test", "TASK-1", { onEvent: (event) => received.push(event.event_id) });
    client.accept({ event_id: "snapshot", task_id: "TASK-1", event_type: "TASK_SNAPSHOT", node: "snapshot", status: "PENDING", timestamp: "now", sequence: 0, data: {} });
    client.accept({ event_id: "evt-1", task_id: "TASK-1", event_type: "INTAKE_STARTED", node: "intake", status: "PROCESSING", timestamp: "now", sequence: 1, data: {} });
    client.accept({ event_id: "evt-1", task_id: "TASK-1", event_type: "INTAKE_STARTED", node: "intake", status: "PROCESSING", timestamp: "now", sequence: 1, data: {} });

    expect(received).toEqual(["snapshot", "evt-1"]);
    expect(client.lastEventId).toBe("evt-1");
  });

  it("keeps replay and live events in sequence order and refetches once for a deduplicated terminal event", () => {
    const received: string[] = []; let terminal = 0;
    const client = new TaskEventClient("http://api.test", "TASK-1", { onEvent: (event) => received.push(event.event_id), onTerminal: () => terminal++ });
    for (const [event_id, event_type, node, sequence] of [["snapshot", "TASK_SNAPSHOT", "snapshot", 0], ["event-2", "MEMORY_COMPLETED", "entity_memory", 2], ["event-3", "ENVIRONMENT_FALLBACK", "environment", 3], ["event-4", "TASK_COMPLETED", "audit", 4], ["late", "INTAKE_STARTED", "intake", 1], ["event-4", "TASK_COMPLETED", "audit", 4]] as const) client.accept({ event_id, task_id: "TASK-1", event_type, node, status: "PROCESSING", timestamp: "now", sequence, data: {} });
    expect(received).toEqual(["snapshot", "event-2", "event-3", "event-4"]);
    expect(client.lastEventId).toBe("event-4");
    expect(terminal).toBe(1);
  });

  it("maps memory, fallback, routing, dispatch, and audit event data without fixed business values", () => {
    const received: unknown[] = [];
    const client = new TaskEventClient("http://api.test", "TASK-1", { onEvent: (event) => received.push(event.data) });
    for (const event of [
      ["MEMORY_COMPLETED", "entity_memory", { memory_id: "dynamic-memory", score: 0.81 }], ["ENVIRONMENT_FALLBACK", "environment", { fallback_reason: "timeout", environment_elapsed_ms: 801 }], ["ROUTING_COMPLETED", "routing", { recommended_route: "dynamic-route", decision: "REROUTE", memory_adopted: true }], ["DISPATCH_COMPLETED", "dispatch", { version: 2, executed: true }], ["AUDIT_COMPLETED", "audit", { result: "APPROVED" }],
    ] as const) client.accept({ event_id: `${event[1]}-${event[0]}`, task_id: "TASK-1", event_type: event[0], node: event[1], status: "PROCESSING", timestamp: "now", sequence: received.length + 1, data: event[2] });
    expect(received).toHaveLength(5);
    expect(received[2]).toMatchObject({ recommended_route: "dynamic-route", memory_adopted: true });
  });

  it("uses a fresh ticket for reconnect, carries last_event_id, and stops after a terminal event", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const issueTicket = vi.fn().mockResolvedValueOnce("ticket-1").mockResolvedValueOnce("ticket-2").mockResolvedValueOnce("ticket-3");
    const client = new TaskEventClient("http://api.test", "TASK-1", { onEvent: () => undefined, issueTicket });

    client.connect();
    await vi.runAllTicks();
    FakeWebSocket.instances[0].emitOpen();
    expect(FakeWebSocket.instances[0].url).toContain("ticket=ticket-1");
    client.accept({ event_id: "event-1", task_id: "TASK-1", event_type: "INTAKE_COMPLETED", node: "intake", status: "PROCESSING", timestamp: "now", sequence: 1, data: {} });
    FakeWebSocket.instances[0].emitClose(1006);
    vi.advanceTimersByTime(999);
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    await vi.runAllTicks();
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(FakeWebSocket.instances[1].url).toContain("ticket=ticket-2");
    expect(FakeWebSocket.instances[1].url).toContain("last_event_id=event-1");

    FakeWebSocket.instances[1].emitClose(1006);
    vi.advanceTimersByTime(1999);
    expect(FakeWebSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1);
    await vi.runAllTicks();
    expect(FakeWebSocket.instances).toHaveLength(3);
    FakeWebSocket.instances[2].emitOpen();

    client.accept({ event_id: "terminal", task_id: "TASK-1", event_type: "TASK_COMPLETED", node: "audit", status: "COMPLETED", timestamp: "now", sequence: 2, data: {} });
    FakeWebSocket.instances[2].emitClose(1006);
    vi.advanceTimersByTime(8000);
    expect(FakeWebSocket.instances).toHaveLength(3);
    expect(issueTicket).toHaveBeenCalledTimes(3);
  });

  it("test_expired_session_stops_websocket_reconnect", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    let active = true;
    const issueTicket = vi.fn().mockResolvedValue("ticket-1");
    const client = new TaskEventClient("http://api.test", "TASK-1", {
      onEvent: () => undefined,
      issueTicket,
      isSessionActive: () => active,
    });
    client.connect();
    await vi.runAllTicks();
    FakeWebSocket.instances[0].emitClose(1006);
    active = false;
    await vi.advanceTimersByTimeAsync(8000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(issueTicket).toHaveBeenCalledOnce();
  });
});
