import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../src/services/api/client";

describe("review decision API client", () => {
  it("posts one authenticated JSON decision to the stable task route", async () => {
    const request = vi.fn().mockResolvedValue({
      status: 200,
      data: {
        task_id: "DEMO-TASK-101",
        decision: "APPROVE",
        status: "APPROVED",
        reviewer: "王主管",
        decided_at: "2026-08-30T10:15:00Z",
        dispatch_version: 2,
      },
    });
    const { createReviewDecisionClient } = await import("../src/services/api/review-decision-client");
    const client = createReviewDecisionClient({ client: { request } as ApiClient });

    const result = await client.decide("DEMO-TASK-101", {
      decision: "APPROVE",
      reason: "同意执行",
    });

    expect(result.status).toBe("APPROVED");
    expect(request).toHaveBeenCalledWith("/api/v1/reviews/DEMO-TASK-101/decision", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: "APPROVE", reason: "同意执行" }),
    });
  });
});

