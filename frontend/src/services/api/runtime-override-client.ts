import { runtimeConfig } from "../../config/runtime";
import type {
  RuntimeInterventionContext,
  RuntimeOverrideDetail,
  RuntimeOverrideHistory,
  RuntimeOverrideRequest,
  RuntimeOverrideResponse,
} from "../../types/runtime-override";
import { createApiClient, type ApiClient } from "./client";

export interface RuntimeOverrideClient {
  getInterventionContext(threadId: string, signal?: AbortSignal): Promise<RuntimeInterventionContext>;
  create(threadId: string, request: RuntimeOverrideRequest, signal?: AbortSignal): Promise<RuntimeOverrideResponse>;
  get(overrideId: string, signal?: AbortSignal): Promise<RuntimeOverrideDetail>;
  listByThread(threadId: string, limit: number, signal?: AbortSignal): Promise<RuntimeOverrideHistory>;
}

export class HttpRuntimeOverrideClient implements RuntimeOverrideClient {
  constructor(private readonly client: ApiClient) {}

  async getInterventionContext(threadId: string, signal?: AbortSignal): Promise<RuntimeInterventionContext> {
    const response = await this.client.request<RuntimeInterventionContext>(
      `/api/v1/runtime/threads/${encodeURIComponent(threadId)}/intervention`,
      { signal },
    );
    return response.data;
  }

  async create(threadId: string, request: RuntimeOverrideRequest, signal?: AbortSignal): Promise<RuntimeOverrideResponse> {
    const response = await this.client.request<RuntimeOverrideResponse>(
      `/api/v1/runtime/threads/${encodeURIComponent(threadId)}/overrides`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal,
      },
    );
    return response.data;
  }

  async get(overrideId: string, signal?: AbortSignal): Promise<RuntimeOverrideDetail> {
    const response = await this.client.request<RuntimeOverrideDetail>(
      `/api/v1/runtime/overrides/${encodeURIComponent(overrideId)}`,
      { signal },
    );
    return response.data;
  }

  async listByThread(threadId: string, limit: number, signal?: AbortSignal): Promise<RuntimeOverrideHistory> {
    const response = await this.client.request<RuntimeOverrideHistory>(
      `/api/v1/runtime/threads/${encodeURIComponent(threadId)}/overrides?limit=${Math.min(Math.max(limit, 1), 100)}`,
      { signal },
    );
    return response.data;
  }
}

export const runtimeOverrideClient = new HttpRuntimeOverrideClient(
  createApiClient({ baseUrl: runtimeConfig.apiBaseUrl }),
);
