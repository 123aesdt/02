import { describe, expect, it, vi } from "vitest";

import { PERMISSIONS, ROLE_PERMISSION_MATRIX } from "../src/auth/permissions";
import { ApiError, createApiClient, type ApiClient } from "../src/services/api/client";
import { createAnomalyReportClient } from "../src/services/api/anomaly-report-client";
import { createAnomalyReportSubmission } from "../src/features/anomaly-report/submission";
import type { AnomalyReportFormInput, AnomalyReportResponse } from "../src/types/anomaly-report";

const form: AnomalyReportFormInput = {
  source_task_id: "TASK-OWNED",
  anomaly_type: "VEHICLE_BREAKDOWN",
  description: "车辆行驶时出现异响，无法继续安全行驶。",
  location_text: "新平路南段物流站入口",
  reported_vehicle_status: "BROKEN",
  severity: "HIGH",
};

const accepted: AnomalyReportResponse = {
  anomaly_id: 42,
  anomaly_no: "ANOM-example",
  task_id: "TASK-NEW",
  status: "PENDING",
  accepted: true,
  duplicate: false,
  message: "问题已上报，AI 调度已启动。",
};

function jsonResponse(body: unknown, status: number) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("anomaly report submission", () => {
  it("posts only the structured report to the stable endpoint", async () => {
    const request = vi.fn().mockResolvedValue({ status: 202, data: accepted });
    const client = createAnomalyReportClient({ client: { request } as ApiClient });

    await client.report({ ...form, idempotency_key: "report-key-1" });

    expect(request).toHaveBeenCalledWith("/api/v1/anomaly-reports", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, idempotency_key: "report-key-1" }),
    });
  });

  it("reuses one idempotency key when queue publication is retried", async () => {
    const calls: string[] = [];
    const report = vi.fn().mockImplementation(async (request) => {
      calls.push(request.idempotency_key);
      if (calls.length === 1) {
        throw new ApiError(503, "REPORT_QUEUE_UNAVAILABLE", "retry");
      }
      return accepted;
    });
    const submission = createAnomalyReportSubmission({ report }, () => "report-key-1");

    await expect(submission.submit(form)).rejects.toMatchObject({
      code: "REPORT_QUEUE_UNAVAILABLE",
    });
    await expect(submission.submit(form)).resolves.toEqual(accepted);
    expect(calls).toEqual(["report-key-1", "report-key-1"]);
  });

  it("grants report permission to employees but not dispatchers", () => {
    expect(ROLE_PERMISSION_MATRIX.EMPLOYEE).toContain(PERMISSIONS.ANOMALIES_REPORT);
    expect(ROLE_PERMISSION_MATRIX.EMPLOYEE).not.toContain(PERMISSIONS.DISPATCH_CREATE);
    expect(ROLE_PERMISSION_MATRIX.DISPATCHER).not.toContain(PERMISSIONS.ANOMALIES_REPORT);
  });

  it("preserves saved anomaly and task identities on a retryable 503", async () => {
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetchImpl: vi.fn().mockResolvedValue(jsonResponse({
        code: "REPORT_QUEUE_UNAVAILABLE",
        message: "问题已保存，但 AI 调度暂未启动。请使用相同内容重试。",
        anomaly_id: 42,
        anomaly_no: "ANOM-example",
        task_id: "TASK-SAVED",
        retryable: true,
      }, 503)),
    });

    await expect(client.request("/api/v1/anomaly-reports")).rejects.toMatchObject({
      status: 503,
      code: "REPORT_QUEUE_UNAVAILABLE",
      details: {
        anomaly_id: 42,
        anomaly_no: "ANOM-example",
        task_id: "TASK-SAVED",
        retryable: true,
      },
    } satisfies Partial<ApiError>);
  });
});
