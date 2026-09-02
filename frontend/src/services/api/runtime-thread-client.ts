import { runtimeConfig } from "../../config/runtime";
import type { RuntimeThreadDetail, RuntimeThreadHistory } from "../../types/runtime-thread";
import { createApiClient, type ApiClient } from "./client";

export interface RuntimeThreadClient {
  getByTask(taskId: string, signal?: AbortSignal): Promise<RuntimeThreadDetail>;
  getHistory(threadId: string, limit: number, signal?: AbortSignal): Promise<RuntimeThreadHistory>;
}

export class HttpRuntimeThreadClient implements RuntimeThreadClient {
  constructor(private readonly client: ApiClient) {}

  async getByTask(taskId: string, signal?: AbortSignal): Promise<RuntimeThreadDetail> {
    const response = await this.client.request<RuntimeThreadDetail>(
      `/api/v1/runtime/threads/by-task/${encodeURIComponent(taskId)}`,
      { signal },
    );
    return response.data;
  }

  async getHistory(threadId: string, limit: number, signal?: AbortSignal): Promise<RuntimeThreadHistory> {
    const response = await this.client.request<RuntimeThreadHistory>(
      `/api/v1/runtime/threads/${encodeURIComponent(threadId)}/history?limit=${limit}`,
      { signal },
    );
    return response.data;
  }
}

export const runtimeThreadClient = new HttpRuntimeThreadClient(
  createApiClient({ baseUrl: runtimeConfig.apiBaseUrl }),
);
