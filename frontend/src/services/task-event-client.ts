import type { TaskEvent } from "../types/task-events";

export function toTaskEventWebSocketUrl(apiBaseUrl: string, taskId: string, ticket: string, lastEventId?: string): string {
  const url = new URL(`/api/v1/ws/tasks/${encodeURIComponent(taskId)}`, apiBaseUrl);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("ticket", ticket);
  if (lastEventId) url.searchParams.set("last_event_id", lastEventId);
  return url.toString();
}

type EventHandler = (event: TaskEvent) => void;
export interface TaskEventClientOptions {
  onEvent: EventHandler;
  onState?: (state: "CONNECTED" | "RECONNECTING" | "DISCONNECTED") => void;
  onTerminal?: () => void;
  issueTicket?: (taskId: string) => Promise<string>;
  isSessionActive?: () => boolean;
}

export class TaskEventClient {
  private seenEventIds = new Set<string>();
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private attempts = 0;
  private disposed = false;
  private terminal = false;
  private highestSequence = -1;
  private connecting = false;
  public lastEventId: string | undefined;

  constructor(private readonly apiBaseUrl: string, private readonly taskId: string, private readonly options: TaskEventClientOptions) {}

  connect(): void {
    if (this.disposed || this.socket || this.connecting || this.options.isSessionActive?.() === false) return;
    this.connecting = true;
    void this.openAuthenticatedSocket();
  }

  private async openAuthenticatedSocket(): Promise<void> {
    try {
      const issueTicket = this.options.issueTicket ?? (await import("./api/ws-ticket-client")).issueTaskWsTicket;
      const ticket = await issueTicket(this.taskId);
      if (this.disposed || this.options.isSessionActive?.() === false) return;
      this.socket = new WebSocket(toTaskEventWebSocketUrl(this.apiBaseUrl, this.taskId, ticket, this.lastEventId));
    } catch {
      if (!this.disposed && this.options.isSessionActive?.() !== false) this.scheduleReconnect();
      return;
    } finally {
      this.connecting = false;
    }
    if (!this.socket) return;
    this.socket.onopen = () => { this.attempts = 0; this.options.onState?.("CONNECTED"); };
    this.socket.onmessage = (message) => {
      try { this.accept(JSON.parse(String(message.data)) as TaskEvent); } catch { return; }
    };
    this.socket.onclose = (event) => {
      this.socket = null;
      if (this.disposed || this.terminal || event.code === 1008) { this.options.onState?.("DISCONNECTED"); return; }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.disposed || this.terminal || this.options.isSessionActive?.() === false) {
      this.options.onState?.("DISCONNECTED");
      return;
    }
    this.options.onState?.("RECONNECTING");
    const delay = Math.min(1000 * 2 ** this.attempts++, 8000);
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }

  accept(event: TaskEvent): void {
    if (event.task_id !== this.taskId || this.seenEventIds.has(event.event_id) || event.sequence < this.highestSequence) return;
    this.seenEventIds.add(event.event_id);
    this.highestSequence = event.sequence;
    if (event.event_type !== "TASK_SNAPSHOT") this.lastEventId = event.event_id;
    this.options.onEvent(event);
    if (["TASK_COMPLETED", "TASK_REVIEW_REQUIRED", "TASK_FAILED"].includes(event.event_type)) {
      this.terminal = true;
      this.options.onTerminal?.();
    }
  }

  close(): void {
    this.disposed = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }
}
