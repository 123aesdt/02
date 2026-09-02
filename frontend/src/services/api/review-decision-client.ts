import { runtimeConfig } from "../../config/runtime";
import { createApiClient, type ApiClient } from "./client";

export type ReviewDecision = "APPROVE" | "REJECT";

export interface ReviewDecisionPayload {
  decision: ReviewDecision;
  reason?: string;
}

export interface ReviewDecisionResponse {
  task_id: string;
  decision: ReviewDecision;
  status: "APPROVED" | "REJECTED";
  reviewer: string;
  decided_at: string;
  dispatch_version: number;
}

export interface ReviewDecisionClient {
  decide(taskId: string, payload: ReviewDecisionPayload): Promise<ReviewDecisionResponse>;
}

export interface ReviewDecisionClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  client?: ApiClient;
}

class HttpReviewDecisionClient implements ReviewDecisionClient {
  constructor(private readonly client: ApiClient) {}

  async decide(taskId: string, payload: ReviewDecisionPayload): Promise<ReviewDecisionResponse> {
    const response = await this.client.request<ReviewDecisionResponse>(
      `/api/v1/reviews/${encodeURIComponent(taskId)}/decision`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    return response.data;
  }
}

export function createReviewDecisionClient(options: ReviewDecisionClientOptions = {}): ReviewDecisionClient {
  const client = options.client ?? createApiClient({
    baseUrl: options.baseUrl ?? runtimeConfig.apiBaseUrl,
    fetchImpl: options.fetchImpl,
  });
  return new HttpReviewDecisionClient(client);
}

export const reviewDecisionClient = createReviewDecisionClient();

