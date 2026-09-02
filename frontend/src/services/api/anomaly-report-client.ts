import { runtimeConfig } from "../../config/runtime";
import type { AnomalyReportRequest, AnomalyReportResponse } from "../../types/anomaly-report";
import { createApiClient, type ApiClient } from "./client";

export interface AnomalyReportClient {
  report(request: AnomalyReportRequest): Promise<AnomalyReportResponse>;
}

export interface AnomalyReportClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  client?: ApiClient;
}

class HttpAnomalyReportClient implements AnomalyReportClient {
  constructor(private readonly client: ApiClient) {}

  async report(request: AnomalyReportRequest): Promise<AnomalyReportResponse> {
    const response = await this.client.request<AnomalyReportResponse>(
      "/api/v1/anomaly-reports",
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      },
    );
    return response.data;
  }
}

export function createAnomalyReportClient(
  options: AnomalyReportClientOptions = {},
): AnomalyReportClient {
  const client = options.client ?? createApiClient({
    baseUrl: options.baseUrl ?? runtimeConfig.apiBaseUrl,
    fetchImpl: options.fetchImpl,
  });
  return new HttpAnomalyReportClient(client);
}

export const anomalyReportClient = createAnomalyReportClient();
