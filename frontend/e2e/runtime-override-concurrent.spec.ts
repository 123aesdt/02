import { expect, test } from "@playwright/test";

import { apiBaseUrl, createRuntimeTask, e2eHeaders, waitForEligibility } from "./support/api";
import { pauseWorkerOne, pauseWorkerTwo, unpauseWorkerOne, unpauseWorkerTwo } from "./support/docker";
import { openOverrideDialog } from "./support/runtime-task";
import { authenticatePage } from "./support/security-auth";

test("test_browser_runtime_override_concurrent", async ({ browser, request }) => {
  pauseWorkerTwo();
  const firstContext = await browser.newContext(); const secondContext = await browser.newContext();
  try {
    const taskId = await createRuntimeTask(request);
    const before = await waitForEligibility(request, taskId, "ELIGIBLE");
    pauseWorkerOne();
    const first = await firstContext.newPage(); const second = await secondContext.newPage();
    await authenticatePage(first, "SUPERVISOR", `/dispatch/${taskId}`);
    await authenticatePage(second, "SUPERVISOR", `/dispatch/${taskId}`);
    const dialogA = await openOverrideDialog(first, taskId, "BROKEN"); const dialogB = await openOverrideDialog(second, taskId, "MAINTENANCE");
    await dialogA.getByLabel("Reason").fill("人工确认车辆爆胎"); await dialogB.getByLabel("Reason").fill("人工确认进入维护");
    await Promise.all([dialogA.getByRole("button", { name: "确认干预" }).click(), dialogB.getByRole("button", { name: "确认干预" }).click()]);
    await expect.poll(async () => {
      const values = await Promise.all([first.locator(".runtime-result").textContent(), second.locator(".runtime-result").textContent()]);
      return values.filter((value) => value?.includes("APPLIED")).length;
    }).toBe(1);
    const threadResponse = await request.get(`${apiBaseUrl}/api/v1/runtime/threads/by-task/${taskId}`, { headers: e2eHeaders() });
    const current = await threadResponse.json(); expect(current.state_version).toBe(before.state_version + 1);
    const historyResponse = await request.get(`${apiBaseUrl}/api/v1/runtime/threads/${encodeURIComponent(before.thread_id)}/overrides?limit=20`, { headers: e2eHeaders() });
    const history = await historyResponse.json(); expect(history.items.filter((item: { status: string }) => item.status === "APPLIED")).toHaveLength(1);
  } finally { await firstContext.close(); await secondContext.close(); try { unpauseWorkerOne(); } catch { /* runner also restores */ } try { unpauseWorkerTwo(); } catch { /* runner also restores */ } }
});
