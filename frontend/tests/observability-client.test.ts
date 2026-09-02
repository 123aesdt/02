import { describe, expect, it, vi } from "vitest";

import { createObservabilityClient, ObservabilityApiError } from "../src/services/api/observability-client";

describe("observability client", () => {
  it("test_frontend_live_metrics", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      state: "LIVE", window: "5m", timestamp: "2026-08-28T00:00:00Z", metrics: { http_qps: 12.5 }, grafana_url: null,
    }), { status: 200 }));

    const result = await createObservabilityClient({ baseUrl: "http://api.test", fetchImpl }).getSummary("5m");

    expect(result.metrics.http_qps).toBe(12.5);
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/v1/observability/summary?window=5m", expect.objectContaining({ signal: undefined }));
  });

  it("test_frontend_api_mode_no_monitoring_mock", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ code: "OBSERVABILITY_UNAVAILABLE" }), { status: 503 }));

    await expect(createObservabilityClient({ baseUrl: "http://api.test", fetchImpl }).getSummary("5m"))
      .rejects.toEqual(expect.objectContaining<Partial<ObservabilityApiError>>({ status: 503 }));
  });
});
