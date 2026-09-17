import type { AnomalyReportClient } from "../../services/api/anomaly-report-client";
import type {
  AnomalyReportFormInput,
  AnomalyReportResponse,
} from "../../types/anomaly-report";

export interface AnomalyReportSubmission {
  submit(input: AnomalyReportFormInput): Promise<AnomalyReportResponse>;
  reset(): void;
}

const REPORTABLE_TASK_STATUSES = new Set([
  "APPROVED",
  "ASSIGNED",
  "PENDING",
  "QUEUED",
  "REVIEW_REQUIRED",
  "RUNNING",
  "PROCESSING",
  "IN_PROGRESS",
]);

export function isTaskReportable(status: string): boolean {
  return REPORTABLE_TASK_STATUSES.has(status);
}

export function createAnomalyReportSubmission(
  client: AnomalyReportClient,
  createRequestId: () => string = () => crypto.randomUUID(),
): AnomalyReportSubmission {
  let idempotencyKey = createRequestId();
  return {
    submit(input) {
      return client.report({ ...input, idempotency_key: idempotencyKey });
    },
    reset() {
      idempotencyKey = createRequestId();
    },
  };
}
