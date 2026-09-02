import type { ObservabilitySummary, ObservabilityWindow } from "../../types/observability";
import { createApiClient } from "./client";

export class ObservabilityApiError extends Error {
  constructor(public readonly status: number) {
    super(status === 403 ? "Monitoring permission is required" : "Monitoring unavailable");
    this.name = "ObservabilityApiError";
  }
}

interface Options {
  baseUrl: string;
  fetchImpl?: typeof fetch;
}

export function createObservabilityClient({ baseUrl, fetchImpl = fetch }: Options) {
  const client = createApiClient({ baseUrl, fetchImpl });
  return {
    async getSummary(window: ObservabilityWindow, signal?: AbortSignal): Promise<ObservabilitySummary> {
      try {
        return (await client.request<ObservabilitySummary>(`/api/v1/observability/summary?window=${window}`, { signal })).data;
      } catch (error) {
        const status = typeof error === "object" && error !== null && "status" in error ? Number(error.status) : 0;
        throw new ObservabilityApiError(status);
      }
    },
  };
}
