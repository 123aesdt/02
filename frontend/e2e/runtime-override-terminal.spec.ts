import { expect, test } from "@playwright/test";

import { apiBaseUrl, createRuntimeTask, e2eHeaders, overrideBody, waitForEligibility, waitForTaskReady } from "./support/api";
import { authenticatePage } from "./support/security-auth";

test("test_browser_runtime_override_terminal", async ({ page, request }) => {
  const taskId = await createRuntimeTask(request); await waitForTaskReady(request, taskId);
  const context = await waitForEligibility(request, taskId, "TERMINAL");
  await authenticatePage(page, "SUPERVISOR", `/dispatch/${taskId}`); await expect(page.getByTestId("runtime-intervention")).toContainText("TERMINAL");
  await expect(page.locator('button[data-target="BROKEN"]')).toBeDisabled();
  const response = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/${encodeURIComponent(context.thread_id)}/overrides`, { headers: e2eHeaders(), data: overrideBody(context, "BROKEN") });
  expect(response.status()).toBe(409); expect((await response.json()).error_code).toBe("THREAD_TERMINAL");
});
