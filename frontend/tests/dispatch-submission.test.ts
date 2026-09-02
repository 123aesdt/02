import { describe, expect, it, vi } from "vitest";

import { coreRainDispatch, createDispatchSubmission } from "../src/features/dispatch/submission";

describe("Dispatch submission", () => {
  it("submits the real Docker seed identities for the core rain scenario", async () => {
    const createDispatchTask = vi.fn().mockResolvedValue({ task_id: "TASK-server-1" });
    const submission = createDispatchSubmission(createDispatchTask, () => "client-request-1");

    await submission.submit(coreRainDispatch);

    expect(createDispatchTask).toHaveBeenCalledWith(expect.objectContaining({
      order_id: 1,
      anomaly_id: 1,
      driver_id: "driver-li",
      vehicle_id: "vehicle-001",
      route_id: "xinping-road",
      anomaly_type: "rain_slippery",
    }));
  });

  it("reuses one generated idempotency key when the same submission is retried", async () => {
    const createDispatchTask = vi.fn().mockResolvedValue({ task_id: "TASK-server-1" });
    const submission = createDispatchSubmission(createDispatchTask, () => "client-request-1");

    await submission.submit({ order_id: 128, anomaly_id: 17, driver_id: "driver-li", vehicle_id: "vehicle-li", route_id: "xinping-road", anomaly_type: "rain_slippery", anomaly_description: "道路湿滑" });
    await submission.submit({ order_id: 128, anomaly_id: 17, driver_id: "driver-li", vehicle_id: "vehicle-li", route_id: "xinping-road", anomaly_type: "rain_slippery", anomaly_description: "道路湿滑" });

    expect(createDispatchTask).toHaveBeenCalledTimes(2);
    expect(createDispatchTask.mock.calls.map(([request]) => request.idempotency_key)).toEqual(["client-request-1", "client-request-1"]);
  });
});
