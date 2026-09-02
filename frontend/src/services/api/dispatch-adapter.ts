import type { ApiClient } from "./client";

export interface CreateDispatchTaskRequest {
  order_id: number;
  anomaly_id: number | null;
  driver_id: string;
  vehicle_id: string;
  route_id: string;
  anomaly_type: string;
  anomaly_description: string;
  idempotency_key: string;
  assignee_employee_id?: string;
}

export interface CreateDispatchTaskResponse {
  task_id: string;
  order_id: number;
  status: string;
  accepted: boolean;
  duplicate: boolean;
  message: string;
}

export interface TaskStatusResponse {
  task_id: string;
  order_id: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  ready: boolean;
  requires_manual_review: boolean;
}

export interface DispatchResultResponse {
  dispatch_id: number;
  dispatch_no: string;
  original_route_id: string | null;
  target_route_id: string | null;
  status: string;
  decision_reason: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  version: number;
  executed: boolean;
}

export interface PublicationResultResponse {
  status: string;
  route_id: string | null;
  route_instruction: string | null;
  published_at: string | null;
  published_by: string | null;
  recipient_employee_id: string | null;
  recipient_display_name: string | null;
}

export interface DispatchPublicationResponse extends PublicationResultResponse {
  task_id: string;
  dispatch_id: number;
  route_id: string;
  route_instruction: string;
  published_at: string;
  published_by: string;
  recipient_employee_id: string;
  recipient_display_name: string;
  duplicate: boolean;
}

export interface AuditResultResponse {
  result: string;
  reason: string;
  dispatch_id: number;
  created_at: string;
}

export interface TaskResultResponse {
  task_id: string;
  order_id: number;
  ready: boolean;
  status: string;
  dispatch: DispatchResultResponse | null;
  audit: AuditResultResponse | null;
  publication?: PublicationResultResponse | null;
}

export interface DispatchAdapter {
  createDispatchTask(request: CreateDispatchTaskRequest, signal?: AbortSignal): Promise<CreateDispatchTaskResponse>;
  getTaskStatus(taskId: string, signal?: AbortSignal): Promise<TaskStatusResponse>;
  getTaskResult(taskId: string, signal?: AbortSignal): Promise<TaskResultResponse>;
  publishDispatchTask(taskId: string, signal?: AbortSignal): Promise<DispatchPublicationResponse>;
}

export class RealDispatchAdapter implements DispatchAdapter {
  constructor(private readonly client: ApiClient) {}

  async createDispatchTask(request: CreateDispatchTaskRequest, signal?: AbortSignal): Promise<CreateDispatchTaskResponse> {
    const response = await this.client.request<CreateDispatchTaskResponse>("/api/v1/dispatch-tasks", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return response.data;
  }

  async getTaskStatus(taskId: string, signal?: AbortSignal): Promise<TaskStatusResponse> {
    const response = await this.client.request<TaskStatusResponse>(`/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}`, { signal });
    return response.data;
  }

  async getTaskResult(taskId: string, signal?: AbortSignal): Promise<TaskResultResponse> {
    const response = await this.client.request<TaskResultResponse>(`/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}/result`, { signal });
    return response.data;
  }

  async publishDispatchTask(taskId: string, signal?: AbortSignal): Promise<DispatchPublicationResponse> {
    const response = await this.client.request<DispatchPublicationResponse>(
      `/api/v1/dispatch-tasks/${encodeURIComponent(taskId)}/publish`,
      { method: "POST", signal },
    );
    return response.data;
  }
}
