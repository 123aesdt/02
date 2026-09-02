import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

import { createRuntimeTask, getThreadByTask, waitForEligibility, waitForTaskReady } from "./support/api";
import { pauseWorkerOne, pauseWorkerTwo, unpauseWorkerOne, unpauseWorkerTwo } from "./support/docker";
import { openOverrideDialog } from "./support/runtime-task";
import { authenticatePage } from "./support/security-auth";

test("test_browser_runtime_override_success", async ({ page, request }) => {
  pauseWorkerTwo();
  const runtimeRequests: string[] = [];
  page.on("request", (outbound) => {
    if (outbound.url().includes("/api/v1/runtime/")) runtimeRequests.push(outbound.url());
  });
  const screenshots = path.resolve(import.meta.dirname, "../../docs/assets/frontend-demo");
  const v2eScreenshots = path.resolve(import.meta.dirname, "../../docs/verification/v2-e/screenshots");
  fs.mkdirSync(v2eScreenshots, { recursive: true });
  try {
    const taskId = await createRuntimeTask(request);
    const before = await waitForEligibility(request, taskId, "ELIGIBLE");
    pauseWorkerOne();
    await authenticatePage(page, "SUPERVISOR", `/dispatch/${taskId}`);
    await expect(page.getByTestId("runtime-intervention")).toContainText("ELIGIBLE");
    const stableWindowBefore = runtimeRequests.length;
    await page.waitForTimeout(1_100);
    const stableWindowAfter = runtimeRequests.length;
    expect(stableWindowAfter).toBe(stableWindowBefore);
    await page.screenshot({ path: path.join(screenshots, "runtime-intervention-eligible.png"), fullPage: true });
    await page.screenshot({ path: path.join(v2eScreenshots, "intervention-eligible.png"), fullPage: true });
    const dialog = await openOverrideDialog(page, taskId, "BROKEN");
    await dialog.getByLabel("Reason").fill("人工确认车辆爆胎");
    await page.screenshot({ path: path.join(screenshots, "runtime-intervention-confirm.png"), fullPage: true });
    await dialog.getByRole("button", { name: "确认干预" }).click();
    const applied = page.locator('[data-submission-state="APPLIED"]');
    await expect(applied).toContainText(`V${before.state_version} → V${before.state_version + 1}`);
    await page.screenshot({ path: path.join(screenshots, "runtime-intervention-applied.png"), fullPage: true });
    await page.screenshot({ path: path.join(v2eScreenshots, "override-applied.png"), fullPage: true });
    const after = await getThreadByTask(request, taskId);
    expect(after.state_version).toBe(before.state_version + 1);
    expect(after.current_checkpoint_id).not.toBe(before.canonical_checkpoint_id);
    unpauseWorkerOne(); unpauseWorkerTwo();
    await expect(page.getByTestId("capacity-evidence").getByText("BROKEN", { exact: true })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("capacity-evidence")).toContainText("vehicle_available = false");
    await page.screenshot({ path: path.join(screenshots, "runtime-intervention-capacity-broken.png"), fullPage: true });
    await page.getByTestId("capacity-evidence").screenshot({ path: path.join(v2eScreenshots, "capacity-broken.png") });
    const final = await waitForTaskReady(request, taskId);
    expect(final.status).toBe("REVIEW_REQUIRED");
    await expect(page.getByRole("heading", { name: "人工复核" }).first()).toBeVisible();
    const endpoints = runtimeRequests.reduce<Record<string, number>>((counts, url) => {
      const endpoint = new URL(url).pathname;
      counts[endpoint] = (counts[endpoint] ?? 0) + 1;
      return counts;
    }, {});
    test.info().annotations.push({
      type: "runtime-request-count",
      description: JSON.stringify({ stable_window: [stableWindowBefore, stableWindowAfter], total: runtimeRequests.length, endpoints }),
    });
    await page.screenshot({ path: path.join(screenshots, "runtime-intervention-review-required.png"), fullPage: true });
    await page.screenshot({ path: path.join(v2eScreenshots, "review-required.png"), fullPage: true });
    await page.locator(".runtime-override-history").screenshot({ path: path.join(v2eScreenshots, "override-history.png") });
    await page.locator(".runtime-event-timeline").screenshot({ path: path.join(v2eScreenshots, "runtime-timeline.png") });
  } finally { try { unpauseWorkerOne(); } catch { /* runner also restores */ } try { unpauseWorkerTwo(); } catch { /* runner also restores */ } }
});
