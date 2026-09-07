import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createApiClient,
} from "../src/services/api/client";
import {
  createDispatchService,
  RealDispatchAdapter,
} from "../src/services/dispatch-service";

const request = {
  order_id: 128,
  anomaly_id: 17,
  driver_id: "driver-li",
  vehicle_id: "vehicle-su-ga8126",
  route_id: "xinping-road",
  anomaly_type: "rain_slippery",
  anomaly_description: "李师傅在雨天经过新平路，道路出现湿滑风险。",
  idempotency_key: "request-1",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Real dispatch API adapter", () => {
  afterEach(() => vi.restoreAllMocks());

  it("test_api_adapter_submits_dispatch_task", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      task_id: "TASK-server-1", order_id: 128, status: "PENDING", accepted: true, duplicate: false, message: "accepted",
    }, 202));
    const adapter = new RealDispatchAdapter(createApiClient({ baseUrl: "http://api.test", fetchImpl: fetchMock }));

    await expect(adapter.createDispatchTask(request)).resolves.toMatchObject({ task_id: "TASK-server-1", accepted: true });
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/api/v1/dispatch-tasks", expect.objectContaining({
      method: "POST", body: JSON.stringify(request),
    }));
  });

  it("test_api_adapter_gets_task_status", async () => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({
        task_id: "TASK-1", order_id: 128, status: "PROCESSING", started_at: null, completed_at: null,
        created_at: "2026-08-22T00:00:00Z", ready: false, requires_manual_review: false,
      })),
    }));

    await expect(adapter.getTaskStatus("TASK-1")).resolves.toMatchObject({ status: "PROCESSING" });
  });

  it("test_api_adapter_gets_task_result", async () => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({
        task_id: "TASK-1", order_id: 128, ready: true, status: "COMPLETED",
        dispatch: { dispatch_id: 1, dispatch_no: "DSP-1", original_route_id: "xinping-road", target_route_id: "national-102", status: "COMPLETED", decision_reason: "safer", fallback_used: true, fallback_reason: "timeout", version: 1, executed: true },
        audit: { result: "APPROVED", reason: "safe", dispatch_id: 1, created_at: "2026-08-22T00:00:00Z" },
      })),
    }));

    await expect(adapter.getTaskResult("TASK-1")).resolves.toMatchObject({ ready: true, dispatch: { target_route_id: "national-102" } });
  });

  it("preserves fleet and route evidence identifiers and decimal strings exactly", async () => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({
        task_id: "TASK-1", order_id: 128, ready: true, status: "COMPLETED", dispatch: null, audit: null,
        vehicle_allocation: { original_vehicle_id: "V-001", target_vehicle_id: "V-005", target_driver_id: "D-003", vehicle_reassigned: true, candidate_vehicles: [{ vehicle_id: "V-005", driver_id: "D-003", pickup_distance_km: "2.80", score: "93.4", exclusion_reasons: [] }], pickup_route: null, scoring_formula: "FLEET_SCORE_V1" },
        route_plan: { original_path: null, recommended_path: null, candidate_routes: [], blocked_edge_ids: ["E04"], distance_delta_km: "3.20", eta_delta_minutes: 4, visited_node_count: 8, routing_status: "ROUTED", algorithm: "DIJKSTRA_V1", road_network_version: 7, network_nodes: [{ node_id: "N01", name: "中心仓", x_km: "0.00", y_km: "0.00", node_type: "DEPOT" }], network_edges: [] },
      })),
    }));

    const result = await adapter.getTaskResult("TASK-1");
    expect(result.vehicle_allocation?.target_vehicle_id).toBe("V-005");
    expect(result.vehicle_allocation?.candidate_vehicles[0]?.pickup_distance_km).toBe("2.80");
    expect(typeof result.vehicle_allocation?.candidate_vehicles[0]?.pickup_distance_km).toBe("string");
    expect(result.route_plan?.blocked_edge_ids).toEqual(["E04"]);
    expect(result.route_plan?.network_nodes[0]?.x_km).toBe("0.00");
    expect(result.route_plan?.distance_delta_km).toBe("3.20");
    expect(typeof result.route_plan?.distance_delta_km).toBe("string");
  });
  it("publishes an approved dispatch through the authenticated task endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      task_id: "TASK-1",
      dispatch_id: 1,
      status: "PUBLISHED",
      route_id: "national-102",
      route_instruction: "从青云镇出发，按 national-102 行驶，前往临港镇。",
      published_at: "2026-08-30T12:00:00Z",
      published_by: "调度主管",
      duplicate: false,
    }));
    const adapter = new RealDispatchAdapter(createApiClient({ baseUrl: "http://api.test", fetchImpl: fetchMock }));

    await expect(adapter.publishDispatchTask("TASK-1")).resolves.toMatchObject({ status: "PUBLISHED", route_id: "national-102" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/v1/dispatch-tasks/TASK-1/publish",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("test_api_adapter_maps_202_not_ready", async () => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({ task_id: "TASK-1", order_id: 128, ready: false, status: "PROCESSING" }, 202)),
    }));
    await expect(adapter.getTaskResult("TASK-1")).resolves.toMatchObject({ ready: false, status: "PROCESSING" });
  });

  it.each([
    [404, "TASK_NOT_FOUND"],
    [409, "IDEMPOTENCY_CONFLICT"],
    [503, "QUEUE_UNAVAILABLE"],
  ])("test_api_adapter_maps_%i", async (status, code) => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({ code, message: "safe message" }, status)),
    }));
    await expect(adapter.getTaskStatus("TASK-1")).rejects.toMatchObject({ status, code, message: "safe message" } satisfies Partial<ApiError>);
  });

  it("maps a FastAPI 422 detail body to a safe validation error", async () => {
    const adapter = new RealDispatchAdapter(createApiClient({
      baseUrl: "http://api.test", fetchImpl: vi.fn().mockResolvedValue(jsonResponse({ detail: [{ loc: ["body", "driver_id"], msg: "Field required" }] }, 422)),
    }));

    await expect(adapter.getTaskStatus("TASK-1")).rejects.toMatchObject({ status: 422, code: "VALIDATION_ERROR", message: "提交信息不完整或格式不正确。" } satisfies Partial<ApiError>);
  });

  it("test_service_uses_mock_adapter_in_mock_mode", async () => {
    const service = createDispatchService({ mode: "mock" });
    await expect(service.getDispatchDetail("TASK-20260821-0042")).resolves.toMatchObject({ taskId: "TASK-20260821-0042" });
  });

  it("test_service_uses_api_adapter_in_api_mode", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      task_id: "TASK-server-1", order_id: 128, status: "PENDING", accepted: true, duplicate: false, message: "accepted",
    }, 202));
    const service = createDispatchService({ mode: "api", baseUrl: "http://api.test", fetchImpl: fetchMock });
    await service.createDispatchTask(request);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("checks backend health through the api-mode service", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: "ok", service: "countyflow-backend", version: "0.1.0" }));
    const service = createDispatchService({ mode: "api", baseUrl: "http://api.test", fetchImpl: fetchMock });

    await expect(service.getBackendHealth()).resolves.toMatchObject({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/health", expect.any(Object));
  });
});
