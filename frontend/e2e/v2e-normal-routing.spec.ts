import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { createRuntimeTask, waitForTaskReady } from "./support/api";
import { authenticatePage } from "./support/security-auth";

test("test_v2e_real_normal_routing_and_graph_memory", async ({ page, request }) => {
  const screenshots = path.resolve(import.meta.dirname, "../../docs/verification/v2-e/screenshots");
  fs.mkdirSync(screenshots, { recursive: true });
  const taskId = await createRuntimeTask(request);
  const result = await waitForTaskReady(request, taskId);
  expect(result.status).toBe("COMPLETED");
  await authenticatePage(page, "DISPATCHER", `/dispatch/${taskId}`);
  await expect(page.getByText("memory-rain-li").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("national-102").first()).toBeVisible();
  await expect(page.getByText("图记忆事件")).toBeVisible();
  await page.screenshot({ path: path.join(screenshots, "normal-routing.png"), fullPage: true });
  await page.locator(".dispatch-result").filter({ hasText: "图记忆事件" }).screenshot({ path: path.join(screenshots, "graph-memory.png") });
});
