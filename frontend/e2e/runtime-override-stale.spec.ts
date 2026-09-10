import { expect, test } from "@playwright/test";

import { apiBaseUrl, createRuntimeTask, e2eHeaders, overrideBody, waitForEligibility } from "./support/api";
import { pauseWorkerOne, pauseWorkerTwo, unpauseWorkerOne, unpauseWorkerTwo } from "./support/docker";
import { openOverrideDialog } from "./support/runtime-task";
import { authenticatePage } from "./support/security-auth";

test("test_browser_runtime_override_stale", async ({ page, request }) => {
  pauseWorkerTwo();
  try {
    const taskId = await createRuntimeTask(request);
    const context = await waitForEligibility(request, taskId, "ELIGIBLE");
    pauseWorkerOne();
    await authenticatePage(page, "SUPERVISOR", `/dispatch/${taskId}`);
    const dialog = await openOverrideDialog(page, taskId, "BROKEN");
    await dialog.getByLabel("干预原因").fill("人工确认车辆爆胎");
    const competing = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/${encodeURIComponent(context.thread_id)}/overrides`, { headers: e2eHeaders(), data: overrideBody(context, "MAINTENANCE") });
    expect(competing.ok()).toBeTruthy();
    await expect(dialog).toContainText("运行状态已变化，请重新发起干预", { timeout: 15_000 });
    await expect(dialog.getByTestId("captured-version")).toHaveText(`版本 ${context.state_version}`);
    await expect(dialog.getByRole("button", { name: "确认干预" })).toBeDisabled();
  } finally { try { unpauseWorkerOne(); } catch { /* runner also restores */ } try { unpauseWorkerTwo(); } catch { /* runner also restores */ } }
});
