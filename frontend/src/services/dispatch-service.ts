import { dashboardSnapshot, dispatchDetail } from "../mocks/dispatch-data";
import { runtimeConfig, type DataMode } from "../config/runtime";
import type { DashboardSnapshot, DispatchDetail } from "../types/dispatch";
import { createApiClient, type ApiClientOptions } from "./api/client";
import {
  RealDispatchAdapter,
  type CreateDispatchTaskRequest,
  type CreateDispatchTaskResponse,
  type DispatchAdapter,
  type DispatchPublicationResponse,
  type TaskResultResponse,
  type TaskStatusResponse,
} from "./api/dispatch-adapter";

export interface BackendHealthResponse {
  status: string;
  service: string;
  version: string;
  runtime?: {
    runtime_profile?: string;
    embedding_provider?: string;
    environment_provider?: string;
    capacity_provider?: string;
    routing_provider?: string;
    database?: string;
    redis?: string;
    qdrant?: string;
    graph_memory?: string;
  };
}

class MockDispatchAdapter implements DispatchAdapter {
  async createDispatchTask(): Promise<CreateDispatchTaskResponse> {
    return { task_id: dispatchDetail.taskId, order_id: 128, status: "COMPLETED", accepted: true, duplicate: false, message: "Demo dispatch task accepted." };
  }

  async getTaskStatus(): Promise<TaskStatusResponse> {
    return { task_id: dispatchDetail.taskId, order_id: 128, status: "COMPLETED", started_at: "2026-08-21T08:12:00Z", completed_at: "2026-08-21T08:14:14Z", created_at: "2026-08-21T08:11:58Z", ready: true, requires_manual_review: false };
  }

  async getTaskResult(): Promise<TaskResultResponse> {
    return {
      task_id: dispatchDetail.taskId,
      order_id: 128,
      ready: true,
      status: "COMPLETED",
      dispatch: {
        dispatch_id: 1, dispatch_no: "DSP-DEMO-1", original_route_id: dispatchDetail.dispatch.originalRoute,
        target_route_id: dispatchDetail.dispatch.targetRoute, status: "COMPLETED", decision_reason: dispatchDetail.decisionReason,
        fallback_used: dispatchDetail.dispatch.fallbackUsed, fallback_reason: dispatchDetail.environment.fallback,
        version: dispatchDetail.dispatch.version, executed: dispatchDetail.dispatch.executed,
      },
      audit: { result: dispatchDetail.audit.status, reason: "Demo audit approved.", dispatch_id: 1, created_at: "2026-08-21T08:14:14Z" },
      publication: { status: "PENDING", route_id: null, route_instruction: null, published_at: null, published_by: null, recipient_employee_id: "CF-DEMO-001", recipient_display_name: "张调度" },
    };
  }

  async publishDispatchTask(): Promise<DispatchPublicationResponse> {
    return {
      task_id: dispatchDetail.taskId,
      dispatch_id: 1,
      status: "PUBLISHED",
      route_id: dispatchDetail.dispatch.targetRoute,
      route_instruction: `请按 ${dispatchDetail.dispatch.targetRoute} 行驶。`,
      published_at: "2026-08-21T08:15:00Z",
      published_by: "演示主管",
      recipient_employee_id: "CF-DEMO-001",
      recipient_display_name: "张调度",
      duplicate: false,
    };
  }
}

export interface DispatchService {
  readonly mode: DataMode;
  getDashboardSnapshot(): Promise<DashboardSnapshot>;
  getDispatchDetail(taskId: string): Promise<DispatchDetail>;
  createDispatchTask(request: CreateDispatchTaskRequest, signal?: AbortSignal): Promise<CreateDispatchTaskResponse>;
  getTaskStatus(taskId: string, signal?: AbortSignal): Promise<TaskStatusResponse>;
  getTaskResult(taskId: string, signal?: AbortSignal): Promise<TaskResultResponse>;
  publishDispatchTask(taskId: string, signal?: AbortSignal): Promise<DispatchPublicationResponse>;
  getBackendHealth(signal?: AbortSignal): Promise<BackendHealthResponse>;
}

export interface DispatchServiceOptions extends Partial<ApiClientOptions> {
  mode?: DataMode;
}

export function createDispatchService({ mode = runtimeConfig.dataMode, baseUrl = runtimeConfig.apiBaseUrl, fetchImpl }: DispatchServiceOptions = {}): DispatchService {
  const client = createApiClient({ baseUrl, fetchImpl });
  const adapter: DispatchAdapter = mode === "api"
    ? new RealDispatchAdapter(client)
    : new MockDispatchAdapter();

  return {
    mode,
    async getDashboardSnapshot() {
      if (mode !== "mock") throw new Error("Dashboard mock snapshot is not available in API mode.");
      return dashboardSnapshot;
    },
    async getDispatchDetail(taskId) {
      if (mode !== "mock") throw new Error("Dispatch detail is loaded from the real task status and result APIs in api mode.");
      if (taskId !== dispatchDetail.taskId) throw new Error("Dispatch task was not found.");
      return dispatchDetail;
    },
    createDispatchTask: (request, signal) => adapter.createDispatchTask(request, signal),
    getTaskStatus: (taskId, signal) => adapter.getTaskStatus(taskId, signal),
    getTaskResult: (taskId, signal) => adapter.getTaskResult(taskId, signal),
    publishDispatchTask: (taskId, signal) => adapter.publishDispatchTask(taskId, signal),
    async getBackendHealth(signal) {
      if (mode === "mock") return { status: "mock", service: "countyflow-frontend", version: "0.1.0" };
      return (await client.request<BackendHealthResponse>("/health", { signal })).data;
    },
  };
}

const dispatchService = createDispatchService();

export async function getDashboardSnapshot(): Promise<DashboardSnapshot> {
  return dispatchService.getDashboardSnapshot();
}

export async function getDispatchDetail(taskId: string): Promise<DispatchDetail> {
  return dispatchService.getDispatchDetail(taskId);
}

export const createDispatchTask = dispatchService.createDispatchTask;
export const getTaskStatus = dispatchService.getTaskStatus;
export const getTaskResult = dispatchService.getTaskResult;
export const publishDispatchTask = dispatchService.publishDispatchTask;
export const getBackendHealth = dispatchService.getBackendHealth;
export { RealDispatchAdapter };
export type { CreateDispatchTaskRequest, CreateDispatchTaskResponse, DispatchPublicationResponse, DispatchResultResponse, PublicationResultResponse, TaskResultResponse, TaskStatusResponse } from "./api/dispatch-adapter";
