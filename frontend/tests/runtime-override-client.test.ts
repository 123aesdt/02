import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../src/services/api/client";
import { HttpRuntimeOverrideClient } from "../src/services/api/runtime-override-client";
import type { RuntimeOverrideRequest } from "../src/types/runtime-override";

const request: RuntimeOverrideRequest = {
  idempotency_key: "runtime-override:attempt-1",
  entity_type: "Vehicle",
  entity_id: "vehicle-001",
  field: "status",
  old_value: "NORMAL",
  new_value: "BROKEN",
  reason: "人工确认车辆爆胎",
  expected_version: 7,
  expected_next_node: "capacity",
};

describe("Runtime override API client", () => {
  it("sends the exact allowlisted command payload", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ override_id: "override-1", status: "APPLIED" }), { status: 200 }));
    const client = new HttpRuntimeOverrideClient(createApiClient({ baseUrl: "http://api.test", fetchImpl }));

    await client.create("cf:dispatch:TASK-1", request);

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/api/v1/runtime/threads/cf%3Adispatch%3ATASK-1/overrides",
      expect.objectContaining({ method: "POST", body: JSON.stringify(request) }),
    );
  });

  it("preserves a structured domain code on HTTP 422", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "OVERRIDE_VALUE_INVALID", message: "OVERRIDE_VALUE_INVALID" }),
      { status: 422 },
    ));
    const client = new HttpRuntimeOverrideClient(createApiClient({ baseUrl: "http://api.test", fetchImpl }));

    await expect(client.create("thread-1", request)).rejects.toMatchObject({
      status: 422,
      code: "OVERRIDE_VALUE_INVALID",
    });
  });

  it("uses VALIDATION_ERROR only for FastAPI field validation details", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: [{ loc: ["body", "reason"], msg: "required" }] }),
      { status: 422 },
    ));
    const client = new HttpRuntimeOverrideClient(createApiClient({ baseUrl: "http://api.test", fetchImpl }));

    await expect(client.create("thread-1", request)).rejects.toMatchObject({ code: "VALIDATION_ERROR" });
  });
});
