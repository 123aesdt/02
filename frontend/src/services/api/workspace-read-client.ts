import { runtimeConfig } from "../../config/runtime";
import type {
  AnomalyFilters,
  AnomalyListItem,
  OrderListItem,
  OrdersFilters,
  OverviewResponse,
  MyTaskFilters,
  MyTaskPageResponse,
  PageFilters,
  PageResponse,
  ReviewListItem,
  RuntimeThreadFilters,
  RuntimeThreadListItem,
  VectorMemoryPageResponse,
} from "../../types/workspace-read-models";
import { createApiClient, type ApiClient } from "./client";

export interface WorkspaceReadClient {
  getOverview(signal?: AbortSignal): Promise<OverviewResponse>;
  getOrders(filters?: OrdersFilters, signal?: AbortSignal): Promise<PageResponse<OrderListItem>>;
  getAnomalies(filters?: AnomalyFilters, signal?: AbortSignal): Promise<PageResponse<AnomalyListItem>>;
  getReviews(filters?: PageFilters, signal?: AbortSignal): Promise<PageResponse<ReviewListItem>>;
  getMyTasks(filters?: MyTaskFilters, signal?: AbortSignal): Promise<MyTaskPageResponse>;
  getRuntimeThreads(filters?: RuntimeThreadFilters, signal?: AbortSignal): Promise<PageResponse<RuntimeThreadListItem>>;
  getVectorMemories(filters?: PageFilters, signal?: AbortSignal): Promise<VectorMemoryPageResponse>;
}

export interface WorkspaceReadClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  client?: ApiClient;
}

function requestPath(path: string, filters: object) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if ((typeof value === "string" || typeof value === "number") && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

class HttpWorkspaceReadClient implements WorkspaceReadClient {
  constructor(private readonly client: ApiClient) {}

  async getOverview(signal?: AbortSignal): Promise<OverviewResponse> {
    return this.request("/api/v1/workspace/overview", signal);
  }

  async getOrders(filters: OrdersFilters = {}, signal?: AbortSignal): Promise<PageResponse<OrderListItem>> {
    return this.requestPage("/api/v1/orders", filters, signal);
  }

  async getAnomalies(filters: AnomalyFilters = {}, signal?: AbortSignal): Promise<PageResponse<AnomalyListItem>> {
    return this.requestPage("/api/v1/anomalies", filters, signal);
  }

  async getReviews(filters: PageFilters = {}, signal?: AbortSignal): Promise<PageResponse<ReviewListItem>> {
    return this.requestPage("/api/v1/reviews", filters, signal);
  }

  async getMyTasks(filters: MyTaskFilters = {}, signal?: AbortSignal): Promise<MyTaskPageResponse> {
    return this.requestPage("/api/v1/my/tasks", filters, signal);
  }

  async getRuntimeThreads(filters: RuntimeThreadFilters = {}, signal?: AbortSignal): Promise<PageResponse<RuntimeThreadListItem>> {
    return this.requestPage("/api/v1/runtime/threads", filters, signal);
  }

  async getVectorMemories(filters: PageFilters = {}, signal?: AbortSignal): Promise<VectorMemoryPageResponse> {
    return this.requestPage("/api/v1/memory/records", filters, signal);
  }

  private async request<T>(path: string, signal?: AbortSignal): Promise<T> {
    const response = await this.client.request<T>(path, { credentials: "same-origin", signal });
    return response.data;
  }

  private async requestPage<T>(path: string, filters: object, signal?: AbortSignal): Promise<T> {
    return this.request<T>(requestPath(path, filters), signal);
  }
}

export function createWorkspaceReadClient(options: WorkspaceReadClientOptions = {}): WorkspaceReadClient {
  const client = options.client ?? createApiClient({
    baseUrl: options.baseUrl ?? runtimeConfig.apiBaseUrl,
    fetchImpl: options.fetchImpl,
  });
  return new HttpWorkspaceReadClient(client);
}

export const workspaceReadClient = createWorkspaceReadClient();
