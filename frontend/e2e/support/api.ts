import { expect, type APIRequestContext } from "@playwright/test";

export const apiBaseUrl = process.env.E2E_API_BASE_URL ?? "http://localhost:8001";

export function e2eHeaders(): Record<string, string> {
  const token = process.env.E2E_ACCESS_TOKEN;
  if (!token) throw new Error("E2E_ACCESS_TOKEN is required for authenticated browser E2E");
  return { Authorization: `Bearer ${token}` };
}

export interface InterventionContext {
  thread_id: string; task_id: string; eligibility: string; state_version: number;
  canonical_checkpoint_id: string | null; next_node: string | null;
  target: { entity_id: string; current_value: string } | null;
}

export async function createRuntimeTask(request: APIRequestContext): Promise<string> {
  const orderId = Number(process.env.E2E_ORDER_ID);
  const anomalyId = Number(process.env.E2E_ANOMALY_ID);
  expect(orderId).toBeGreaterThan(0); expect(anomalyId).toBeGreaterThan(0);
  const response = await request.post(`${apiBaseUrl}/api/v1/dispatch-tasks`, { headers: e2eHeaders(), data: {
    order_id: orderId, anomaly_id: anomalyId, driver_id: "driver-li", vehicle_id: "vehicle-001",
    route_id: "xinping-road", anomaly_type: "rain_slippery",
    anomaly_description: "李师傅在雨天经过新平路，道路出现湿滑风险。",
    idempotency_key: `browser-e2e-${crypto.randomUUID()}`,
  } });
  expect(response.status()).toBe(202);
  return (await response.json()).task_id as string;
}

export async function getThreadByTask(request: APIRequestContext, taskId: string) {
  const response = await request.get(`${apiBaseUrl}/api/v1/runtime/threads/by-task/${encodeURIComponent(taskId)}`, { headers: e2eHeaders() });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function getIntervention(request: APIRequestContext, threadId: string): Promise<InterventionContext> {
  const response = await request.get(`${apiBaseUrl}/api/v1/runtime/threads/${encodeURIComponent(threadId)}/intervention`, { headers: e2eHeaders() });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function waitForEligibility(request: APIRequestContext, taskId: string, eligibility: string): Promise<InterventionContext> {
  let last: InterventionContext | null = null;
  await expect.poll(async () => {
    const thread = await getThreadByTask(request, taskId);
    last = await getIntervention(request, thread.thread_id as string);
    return last?.eligibility;
  }, { timeout: 30_000, intervals: [25, 50, 100] }).toBe(eligibility);
  return last!;
}

export function overrideBody(context: InterventionContext, newValue: "BROKEN" | "UNAVAILABLE" | "MAINTENANCE") {
  return {
    idempotency_key: `runtime-override:${crypto.randomUUID()}`, entity_type: "Vehicle", entity_id: "vehicle-001",
    field: "status", old_value: "NORMAL", new_value: newValue, reason: "人工确认车辆爆胎",
    expected_version: context.state_version, expected_next_node: "capacity",
  };
}

export async function waitForTaskReady(request: APIRequestContext, taskId: string) {
  let result: Record<string, unknown> = {};
  await expect.poll(async () => {
    const response = await request.get(`${apiBaseUrl}/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}`, { headers: e2eHeaders() });
    result = await response.json();
    return result.ready;
  }, { timeout: 35_000, intervals: [250, 500, 1000] }).toBe(true);
  return result;
}
