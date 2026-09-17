import { runtimeConfig } from "../../config/runtime";
import { createApiClient, type ApiClient } from "./client";

export type DemoScenarioId = "VEHICLE_BREAKDOWN_N04" | "ROAD_BLOCKED_E04";

export interface DemoScenarioResetResponse {
  scenario_id: DemoScenarioId;
  status: "READY";
  message: string;
}

export interface DemoScenarioClient {
  reset(scenarioId: DemoScenarioId): Promise<DemoScenarioResetResponse>;
}

export interface DemoScenarioClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  client?: ApiClient;
}

class HttpDemoScenarioClient implements DemoScenarioClient {
  constructor(private readonly client: ApiClient) {}

  async reset(scenarioId: DemoScenarioId): Promise<DemoScenarioResetResponse> {
    const response = await this.client.request<DemoScenarioResetResponse>(
      `/api/v1/demo-scenarios/${scenarioId}/reset`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      },
    );
    return response.data;
  }
}

export function createDemoScenarioClient(
  options: DemoScenarioClientOptions = {},
): DemoScenarioClient {
  const client = options.client ?? createApiClient({
    baseUrl: options.baseUrl ?? runtimeConfig.apiBaseUrl,
    fetchImpl: options.fetchImpl,
  });
  return new HttpDemoScenarioClient(client);
}

export const demoScenarioClient = createDemoScenarioClient();
