import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiBaseUrl, createRuntimeTask, getThreadByTask, waitForEligibility, waitForTaskReady } from "./support/api";
import { pauseWorkerOne, pauseWorkerTwo, unpauseWorkerOne, unpauseWorkerTwo } from "./support/docker";
import { openOverrideDialog } from "./support/runtime-task";

const screenshotDir = path.resolve(import.meta.dirname, "../../docs/verification/v2-f/screenshots");

async function createSharedMemoryFact(request: APIRequestContext): Promise<string> {
  const now = new Date();
  const response = await request.post(`${apiBaseUrl}/api/v1/memory/mutations`, {
    data: {
      idempotency_key: `v2f-browser-${crypto.randomUUID()}`,
      category: "DispatchMemory",
      fact_kind: "RELATIONSHIP",
      subject_type: "Vehicle",
      subject_id: `v2f-vehicle-${crypto.randomUUID()}`,
      predicate: "STATUS",
      object_type: "Route",
      object_id: "xinping-road",
      value_json: { status: "BROKEN", source: "V2-F browser acceptance" },
      expected_version: null,
      confidence: "0.9900",
      incoming_at: now.toISOString(),
      expires_at: new Date(now.getTime() + 86_400_000).toISOString(),
      source_type: "v2f_browser",
      source_id: "productization-flow",
      operator_id: "v2f-browser",
      human_confirmed: true,
      reason: "V2-F Shared Memory Control Plane browser evidence",
      evidence_text: "Real MySQL and Neo4j projection",
      evidence_observed_at: now.toISOString(),
      graph_fact_key: `v2f-browser-graph-${crypto.randomUUID()}`,
      targets: ["GRAPH"],
    },
  });
  expect([200, 202]).toContain(response.status());
  const result = await response.json();
  expect(result.status).toBe("APPLIED");
  return result.fact_key as string;
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test("V2-F product surfaces expose live V2 evidence without mock fallback", async ({ page, request }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const taskId = await createRuntimeTask(request);
  const normalResult = await waitForTaskReady(request, taskId);
  expect(normalResult.ready).toBe(true);
  const factKey = await createSharedMemoryFact(request);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible();
  await expect(page.getByText("VERIFIED ACCEPTANCE", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("业务汇总接口未暴露")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "dashboard-v2.png"), fullPage: true });

  await page.getByRole("link", { name: "智能体中心" }).click();
  await page.getByLabel("Task ID").fill(taskId);
  await expect(page.getByText("GRAPH_MEMORY_COMPLETED", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("8 / 8", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "agents-8-pipeline.png"), fullPage: true });

  await page.getByRole("link", { name: "记忆中心" }).click();
  await expect(page.getByRole("tab", { name: "Vector Memory" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("当前后端未暴露 Vector Memory 浏览 API")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "memory-vector.png"), fullPage: true });

  await page.getByRole("tab", { name: "Graph Memory" }).click();
  await page.getByLabel("Task ID").fill(taskId);
  await expect(page.getByRole("img", { name: "Graph Memory entity relationships" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Path Inspector" })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "memory-graph.png"), fullPage: true });

  await page.getByRole("tab", { name: "Shared Control" }).click();
  await page.getByLabel("Canonical fact key").fill(factKey);
  await expect(page.getByText(factKey, { exact: true })).toBeVisible();
  await expect(page.getByText("Memory Mutation History")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "memory-shared-control.png"), fullPage: true });

  let workerOnePaused = false;
  let workerTwoStopped = false;
  try {
    pauseWorkerTwo();
    workerTwoStopped = true;
    const overrideTaskId = await createRuntimeTask(request);
    const before = await waitForEligibility(request, overrideTaskId, "ELIGIBLE");
    pauseWorkerOne();
    workerOnePaused = true;
    await page.goto(`/dispatch/${encodeURIComponent(overrideTaskId)}`);
    await expect(page.getByRole("region", { name: "Runtime Thread" })).toBeVisible();
    await page.getByRole("region", { name: "Runtime Thread" }).screenshot({ path: path.join(screenshotDir, "dispatch-runtime-thread.png") });
    await expect(page.getByTestId("runtime-intervention")).toContainText("ELIGIBLE");
    await page.getByTestId("runtime-intervention").screenshot({ path: path.join(screenshotDir, "intervention-eligible.png") });
    await page.locator(".checkpoint-timeline").screenshot({ path: path.join(screenshotDir, "checkpoint-timeline.png") });

    const dialog = await openOverrideDialog(page, overrideTaskId, "BROKEN");
    await dialog.getByLabel("Reason").fill("人工确认车辆爆胎");
    await dialog.getByRole("button", { name: "确认干预" }).click();
    const applied = page.locator('[data-submission-state="APPLIED"]');
    await expect(applied).toContainText(`V${before.state_version} → V${before.state_version + 1}`);
    await page.getByTestId("runtime-intervention").screenshot({ path: path.join(screenshotDir, "intervention-applied.png") });
    const after = await getThreadByTask(request, overrideTaskId);
    expect(after.state_version).toBe(before.state_version + 1);

    unpauseWorkerOne();
    workerOnePaused = false;
    unpauseWorkerTwo();
    workerTwoStopped = false;
    await expect(page.getByTestId("capacity-evidence").getByText("BROKEN", { exact: true })).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("capacity-evidence").screenshot({ path: path.join(screenshotDir, "capacity-broken.png") });
    const finalResult = await waitForTaskReady(request, overrideTaskId);
    expect(finalResult.status).toBe("REVIEW_REQUIRED");
    await expect(page.locator(".runtime-override-history")).toContainText("APPLIED");
    await page.locator(".runtime-override-history").screenshot({ path: path.join(screenshotDir, "override-history.png") });
  } finally {
    if (workerOnePaused) try { unpauseWorkerOne(); } catch { /* final restoration */ }
    if (workerTwoStopped) try { unpauseWorkerTwo(); } catch { /* final restoration */ }
  }

  await page.getByRole("link", { name: "系统监控" }).click();
  await expect(page.getByText("VERIFIED ACCEPTANCE", { exact: true })).toBeVisible();
  await expect(page.getByText("来自现有 V2-E 验收证据，非实时监控。", { exact: true })).toBeVisible();
  await expect(page.getByText("Neo4j", { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "monitoring-v2.png"), fullPage: true });
  await expectNoHorizontalOverflow(page);

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "系统监控" })).toBeVisible();
  await expectNoHorizontalOverflow(page);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  test.info().annotations.push({
    type: "v2-f-browser-health",
    description: JSON.stringify({ console_errors: 0, page_errors: 0, viewports: [1440, 1920], screenshots: 12 }),
  });
});
