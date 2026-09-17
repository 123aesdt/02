import { describe, expect, it, vi } from "vitest";

import { createDemoScenarioClient } from "../src/services/api/demo-scenario-client";
import type { ApiClient } from "../src/services/api/client";

describe("demo scenario client", () => {
  it("resets only the selected demo scenario through the dedicated endpoint", async () => {
    const payload = {
      scenario_id: "VEHICLE_BREAKDOWN_N04",
      status: "READY" as const,
      message: "演示场景已恢复，可以再次提交。",
    };
    const request = vi.fn().mockResolvedValue({ status: 200, data: payload });
    const client = createDemoScenarioClient({ client: { request } as ApiClient });

    await expect(client.reset("VEHICLE_BREAKDOWN_N04")).resolves.toEqual(payload);

    expect(request).toHaveBeenCalledWith(
      "/api/v1/demo-scenarios/VEHICLE_BREAKDOWN_N04/reset",
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      },
    );
  });
});
