import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { RuntimeWorkbench } from "../src/components/runtime-workbench";
import { ApiError } from "../src/services/api/client";
import type { RuntimeOverrideClient } from "../src/services/api/runtime-override-client";
import type { RuntimeThreadClient } from "../src/services/api/runtime-thread-client";
import type { RuntimeInterventionContext, RuntimeOverrideResponse } from "../src/types/runtime-override";
import type { RuntimeThreadDetail } from "../src/types/runtime-thread";
import type { TaskEvent } from "../src/types/task-events";
import { clearSession, setAuthenticatedSession } from "../src/auth/session";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const thread: RuntimeThreadDetail = {
  thread_id: "cf:dispatch:TASK-1", task_id: "TASK-1", status: "STABLE", terminal: false,
  current_checkpoint_id: "checkpoint-7", state_version: 7, current_node: "environment", next_node: "capacity",
  checkpoint_count: 7, checkpoint_size_bytes: 900, last_event_sequence: 10, checkpoint_available: true,
  worker_consumer: "worker-county-01",
  state: null, created_at: "2026-08-27T00:00:00Z", updated_at: "2026-08-27T00:00:01Z", terminal_at: null,
};

const eligible: RuntimeInterventionContext = {
  thread_id: thread.thread_id, task_id: thread.task_id, runtime_status: "STABLE", state_version: 7,
  current_node: "environment", next_node: "capacity", canonical_checkpoint_id: "checkpoint-7",
  checkpoint_available: true, eligibility: "ELIGIBLE", eligibility_reason_code: null, can_override: true,
  target: { entity_type: "Vehicle", entity_id: "vehicle-001", display_name: "冷链车A", field: "status", current_value: "NORMAL", allowed_new_values: ["BROKEN", "UNAVAILABLE", "MAINTENANCE"] },
  observed_at: "2026-08-27T00:00:01Z",
};

function response(overrides: Partial<RuntimeOverrideResponse> = {}): RuntimeOverrideResponse {
  return {
    override_id: "override-1", thread_id: thread.thread_id, task_id: thread.task_id,
    operator_id: "dispatcher-1", operator_role: "dispatcher", status: "APPLIED", decision: "ALLOWED",
    expected_version: 7, expected_next_node: "capacity", before_state_version: 7, after_state_version: 8,
    entity_type: "Vehicle", entity_id: "vehicle-001", field: "status", old_value: "NORMAL", new_value: "BROKEN",
    reason: "人工确认车辆爆胎", source_checkpoint_id: "checkpoint-7", result_checkpoint_id: "checkpoint-8",
    event_status: "PUBLISHED", error_code: null, requested_at: "2026-08-27T00:00:01Z",
    started_at: "2026-08-27T00:00:01Z", completed_at: "2026-08-27T00:00:02Z", replayed: false,
    ...overrides,
  };
}

function threadClient(): RuntimeThreadClient {
  return {
    getByTask: vi.fn().mockResolvedValue(thread),
    getHistory: vi.fn().mockResolvedValue({ thread_id: thread.thread_id, items: [] }),
  };
}

function overrideClient(context: RuntimeInterventionContext = eligible): RuntimeOverrideClient {
  return {
    getInterventionContext: vi.fn().mockResolvedValue(context),
    create: vi.fn().mockResolvedValue(response()),
    get: vi.fn().mockResolvedValue(response({ status: "PARTIAL" })),
    listByThread: vi.fn().mockResolvedValue({ thread_id: thread.thread_id, items: [] }),
  };
}

function event(eventId: string, eventType: string, sequence = 11, data: Record<string, unknown> = {}): TaskEvent {
  return { event_id: eventId, task_id: "TASK-1", event_type: eventType, node: "runtime_override", status: "PROCESSING", timestamp: "2026-08-27T00:00:02Z", sequence, data };
}

async function renderWorkbench(props: Partial<React.ComponentProps<typeof RuntimeWorkbench>> = {}) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const defaults: React.ComponentProps<typeof RuntimeWorkbench> = {
    taskId: "TASK-1", enabled: true, mode: "api", events: [], threadClient: threadClient(), overrideClient: overrideClient(),
  };
  const values = { ...defaults, ...props };
  await act(async () => { root.render(<RuntimeWorkbench {...values} />); });
  await flush();
  return { root, container, props: values };
}

async function flush(): Promise<void> {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

async function click(container: HTMLElement, text: string): Promise<HTMLButtonElement> {
  const button = [...container.querySelectorAll("button")].find((item) => item.textContent?.includes(text));
  if (!button) throw new Error(`Missing button: ${text}`);
  await act(async () => { button.click(); });
  return button;
}

async function enterReason(container: HTMLElement, value = "人工确认车辆爆胎"): Promise<void> {
  const input = container.querySelector("textarea");
  if (!input) throw new Error("Missing reason textarea");
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  await act(async () => { setter?.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); });
}

async function openBroken(container: HTMLElement): Promise<void> {
  await click(container, "故障");
}

beforeEach(() => {
  vi.spyOn(crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001");
  setAuthenticatedSession("test-token", {
    subject_id: "test-admin", display_name: "Test Admin", roles: ["ADMIN"],
    permissions: ["runtime:read", "runtime:override"], auth_method: "development_jwt",
    issued_at: "2026-08-28T00:00:00Z", expires_at: "2099-08-28T01:00:00Z",
  });
});
afterEach(() => { clearSession(); vi.restoreAllMocks(); vi.useRealTimers(); document.body.replaceChildren(); });

it("test_override_panel_eligible", async () => {
  const intervalSpy = vi.spyOn(window, "setInterval");
  const api = overrideClient();
  const threads = threadClient();
  const { container } = await renderWorkbench({ overrideClient: api, threadClient: threads });
  expect(["BROKEN", "UNAVAILABLE", "MAINTENANCE"].every((value) => !container.querySelector<HTMLButtonElement>(`button[data-target="${value}"]`)?.disabled)).toBe(true);
  expect(container.textContent).toContain("故障"); expect(container.textContent).toContain("不可用"); expect(container.textContent).toContain("维护中");
  expect(threads.getByTask).toHaveBeenCalledOnce();
  expect(api.getInterventionContext).toHaveBeenCalledOnce();
  expect(api.listByThread).toHaveBeenCalledWith(thread.thread_id, 20, expect.any(AbortSignal));
  expect(intervalSpy).not.toHaveBeenCalled();
});

it("test_override_panel_not_stable_disabled", async () => {
  const { container } = await renderWorkbench({ overrideClient: overrideClient({ ...eligible, eligibility: "NOT_STABLE", runtime_status: "RUNNING" }) });
  expect(container.textContent).toContain("智能体正在执行");
  expect([...container.querySelectorAll<HTMLButtonElement>("button[data-target]")].every((button) => button.disabled)).toBe(true);
});

it("test_override_panel_terminal_disabled", async () => {
  const { container } = await renderWorkbench({ overrideClient: overrideClient({ ...eligible, eligibility: "TERMINAL", runtime_status: "TERMINAL" }) });
  expect(container.textContent).toContain("任务已经结束");
  expect(container.querySelector<HTMLButtonElement>('button[data-target="BROKEN"]')?.disabled).toBe(true);
});

it("test_override_permission", async () => {
  const { container } = await renderWorkbench({ overrideClient: overrideClient({ ...eligible, eligibility: "NO_PERMISSION", can_override: false }) });
  expect(container.textContent).toContain("无权限执行运行态强干预");
  expect(container.querySelector<HTMLButtonElement>('button[data-target="BROKEN"]')?.disabled).toBe(true);
});

it("test_override_dialog_shows_version", async () => {
  const { container } = await renderWorkbench(); await openBroken(container);
  const dialog = container.querySelector('[role="dialog"]');
  expect(dialog?.textContent).toContain("冷链车A"); expect(dialog?.textContent).toContain("正常 → 故障");
  expect(dialog?.textContent).toContain("版本 7"); expect(dialog?.textContent).toContain("checkpoint-7"); expect(dialog?.textContent).toContain("运力");
});

it("test_override_dialog_supports_focus_and_escape", async () => {
  const { container } = await renderWorkbench();
  const trigger = await click(container, "故障");
  const reason = container.querySelector('textarea[aria-label="干预原因"]');
  expect(document.activeElement).toBe(reason);
  await act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); });
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("test_override_reason_required", async () => {
  const { container } = await renderWorkbench(); await openBroken(container);
  const confirm = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("确认干预"));
  expect(confirm?.disabled).toBe(true); await enterReason(container, "   "); expect(confirm?.disabled).toBe(true);
  await enterReason(container, "爆胎确认"); expect(confirm?.disabled).toBe(false);
});

it("test_override_submit_payload", async () => {
  const api = overrideClient(); const { container } = await renderWorkbench({ overrideClient: api });
  await openBroken(container); await enterReason(container); await click(container, "确认干预");
  expect(api.create).toHaveBeenCalledWith(thread.thread_id, {
    idempotency_key: "runtime-override:00000000-0000-4000-8000-000000000001", entity_type: "Vehicle", entity_id: "vehicle-001", field: "status",
    old_value: "NORMAL", new_value: "BROKEN", reason: "人工确认车辆爆胎", expected_version: 7, expected_next_node: "capacity",
  });
});

it("test_override_success_updates_version", async () => {
  const { container } = await renderWorkbench(); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush();
  expect(container.textContent).toContain("已应用"); expect(container.textContent).toContain("V7 → V8"); expect(container.textContent).toContain("checkpoint-8");
});

it("test_override_stale_dialog", async () => {
  const api = overrideClient(); vi.mocked(api.getInterventionContext).mockResolvedValueOnce(eligible).mockResolvedValue({ ...eligible, state_version: 8, canonical_checkpoint_id: "checkpoint-8" });
  const view = await renderWorkbench({ overrideClient: api }); await openBroken(view.container);
  await act(async () => { view.root.render(<RuntimeWorkbench {...view.props} events={[event("checkpointed", "THREAD_CHECKPOINTED")]} />); }); await flush();
  expect(view.container.textContent).toContain("运行状态已变化，请重新发起干预");
});

it("test_override_version_conflict_ui", async () => {
  const api = overrideClient(); vi.mocked(api.create).mockRejectedValue(new ApiError(409, "RUNTIME_STATE_VERSION_CONFLICT", "conflict"));
  const { container } = await renderWorkbench({ overrideClient: api }); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush();
  expect(container.textContent).toContain("运行状态已变化，请刷新后重试");
});

it("test_override_busy_ui", async () => {
  const api = overrideClient(); vi.mocked(api.create).mockRejectedValue(new ApiError(409, "RUNTIME_OVERRIDE_BUSY", "busy"));
  const { container } = await renderWorkbench({ overrideClient: api }); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush();
  expect(container.textContent).toContain("当前 Thread 正在被其他操作修改");
});

it("test_override_partial_ui", async () => {
  vi.useFakeTimers(); const api = overrideClient(); vi.mocked(api.create).mockResolvedValue(response({ status: "PARTIAL", after_state_version: null }));
  const { container } = await renderWorkbench({ overrideClient: api }); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush();
  expect(container.textContent).toContain("状态修改正在恢复，请勿重复提交新的干预");
  await act(async () => { await vi.advanceTimersByTimeAsync(14000); });
  expect(api.get).toHaveBeenCalledTimes(3); expect(api.create).toHaveBeenCalledOnce();
});

it("test_override_applied_event", async () => {
  const applied = event("applied-1", "RUNTIME_OVERRIDE_APPLIED", 12, { operator_id: "dispatcher-1", reason: "人工确认车辆爆胎", old_value: "NORMAL", new_value: "BROKEN", before_state_version: 7, after_state_version: 8 });
  const { container } = await renderWorkbench({ events: [applied] });
  expect(container.textContent).toContain("dispatcher-1"); expect(container.textContent).toContain("正常 → 故障"); expect(container.textContent).toContain("V7 → V8");
});

it("test_override_history", async () => {
  const api = overrideClient(); vi.mocked(api.listByThread).mockResolvedValue({ thread_id: thread.thread_id, items: [response()] });
  const { container } = await renderWorkbench({ overrideClient: api });
  expect(container.textContent).toContain("dispatcher-1"); expect(container.textContent).toContain("人工确认车辆爆胎"); expect(container.textContent).not.toContain("runtime-override:attempt");
  expect(container.textContent).toContain("车辆 vehicle-001 · 状态");
  expect(container.textContent).toContain("checkpoint-7 → checkpoint-8");
  expect(container.textContent).toContain("2026-08-27T00:00:02Z");
});

it("test_capacity_displays_broken_vehicle", async () => {
  const capacity = event("capacity-1", "CAPACITY_COMPLETED", 13, { vehicle_id: "vehicle-001", vehicle_status: "BROKEN", vehicle_available: false, capacity_status: "UNAVAILABLE", reason: "Vehicle runtime status is BROKEN." });
  const { container } = await renderWorkbench({ events: [capacity] });
  expect(container.textContent).toContain("车辆 vehicle-001"); expect(container.textContent).toContain("故障"); expect(container.textContent).toContain("车辆可用：否");
});

it("test_api_mode_no_mock_override", async () => {
  const api = overrideClient(); vi.mocked(api.getInterventionContext).mockRejectedValue(new Error("offline"));
  const { container } = await renderWorkbench({ mode: "api", overrideClient: api });
  expect(container.textContent).toContain("运行时干预暂时不可用"); expect(container.textContent).not.toContain("Mock APPLIED");
});

it("test_mock_mode_override_isolated", async () => {
  const api = overrideClient(); const threads = threadClient();
  const { container } = await renderWorkbench({ mode: "mock", overrideClient: api, threadClient: threads });
  expect(container.textContent).toContain("演示数据"); expect(container.textContent).toContain("故障");
  expect(api.getInterventionContext).not.toHaveBeenCalled(); expect(threads.getByTask).not.toHaveBeenCalled();
});

it("test_stale_dialog_does_not_rebase_version", async () => {
  const api = overrideClient(); vi.mocked(api.getInterventionContext).mockResolvedValueOnce(eligible).mockResolvedValue({ ...eligible, state_version: 8, canonical_checkpoint_id: "checkpoint-8" });
  const view = await renderWorkbench({ overrideClient: api }); await openBroken(view.container); await enterReason(view.container);
  await act(async () => { view.root.render(<RuntimeWorkbench {...view.props} events={[event("checkpointed", "THREAD_CHECKPOINTED")]} />); }); await flush();
  const dialog = view.container.querySelector('[role="dialog"]'); expect(dialog?.textContent).toContain("发起时版本 7"); expect(dialog?.textContent).toContain("当前版本 8");
  expect([...dialog!.querySelectorAll("button")].find((button) => button.textContent?.includes("确认干预"))?.disabled).toBe(true);
  expect(api.create).not.toHaveBeenCalled();
});

it("test_override_retry_reuses_idempotency_key", async () => {
  const api = overrideClient(); vi.mocked(api.create).mockRejectedValueOnce(new ApiError(503, "CHECKPOINT_STORE_UNAVAILABLE", "offline")).mockResolvedValueOnce(response());
  const { container } = await renderWorkbench({ overrideClient: api }); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush(); await click(container, "重试同一操作"); await flush();
  expect(api.create).toHaveBeenCalledTimes(2); expect(vi.mocked(api.create).mock.calls[0][1].idempotency_key).toBe(vi.mocked(api.create).mock.calls[1][1].idempotency_key);
});

it("test_applied_does_not_depend_on_websocket_event", async () => {
  const { container } = await renderWorkbench({ events: [] }); await openBroken(container); await enterReason(container); await click(container, "确认干预"); await flush();
  expect(container.querySelector('[data-submission-state="APPLIED"]')?.textContent).toContain("已应用");
});

it("test_duplicate_override_event_does_not_duplicate_timeline", async () => {
  const duplicate = event("same-id", "RUNTIME_OVERRIDE_APPLIED", 12, { old_value: "NORMAL", new_value: "BROKEN" });
  const { container } = await renderWorkbench({ events: [duplicate, duplicate] });
  expect(container.querySelectorAll('[data-event-id="same-id"]')).toHaveLength(1);
});

it("test_runtime_timeline_uses_operator_semantics", async () => {
  const events = [
    event("environment", "ENVIRONMENT_COMPLETED", 10),
    event("override", "RUNTIME_OVERRIDE_APPLIED", 11, { old_value: "NORMAL", new_value: "BROKEN", before_state_version: 7, after_state_version: 8 }),
    event("capacity", "CAPACITY_COMPLETED", 12, { vehicle_status: "BROKEN", vehicle_available: false }),
    event("routing", "ROUTING_COMPLETED", 13, { decision: "REVIEW_REQUIRED" }),
    event("audit", "AUDIT_COMPLETED", 14, { audit_result: { audit_status: "APPROVED" } }),
  ];
  const { container } = await renderWorkbench({ events });
  expect(container.textContent).toContain("环境节点已完成");
  expect(container.textContent).toContain("车辆 正常 → 故障");
  expect(container.textContent).toContain("运力读取到故障 · 车辆不可用");
  expect(container.textContent).toContain("路线已重新计算 · 需要复核");
  expect(container.textContent).toContain("审核已记录 · 已批准");
});
