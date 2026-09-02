import type { CreateDispatchTaskRequest, CreateDispatchTaskResponse } from "../../services/dispatch-service";

export type DispatchSubmissionInput = Omit<CreateDispatchTaskRequest, "idempotency_key">;

type SubmitTask = (request: CreateDispatchTaskRequest) => Promise<CreateDispatchTaskResponse>;

export function createDispatchSubmission(submitTask: SubmitTask, createRequestId: () => string = () => crypto.randomUUID()) {
  const idempotencyKey = createRequestId();
  return {
    submit(input: DispatchSubmissionInput) {
      return submitTask({ ...input, idempotency_key: idempotencyKey });
    },
  };
}

export const coreRainDispatch: DispatchSubmissionInput = {
  order_id: 1,
  anomaly_id: 1,
  driver_id: "driver-li",
  vehicle_id: "vehicle-001",
  route_id: "xinping-road",
  anomaly_type: "rain_slippery",
  anomaly_description: "李师傅在雨天经过新平路，道路出现湿滑风险。",
};
