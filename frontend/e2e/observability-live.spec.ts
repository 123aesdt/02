import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

test("实时可观测性与验收基线保持分离", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await authenticatePage(page, "OPERATOR", "/monitor");
  await expect(page.getByText("实时可观测性", { exact: true })).toBeVisible();
  await expect(page.getByText("已通过验收", { exact: true })).toBeVisible();
  await expect(page.locator(".live-observability-panel .source-label")).toHaveText(/实时|数据陈旧/);
  await expect(page.getByText("演示数据", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/MySQL (正常|异常)/)).toBeVisible();
  const screenshotDirectory = path.resolve(import.meta.dirname, "../../docs/verification/v2-g1/screenshots");
  fs.mkdirSync(screenshotDirectory, { recursive: true });
  await page.screenshot({ path: path.join(screenshotDirectory, "monitoring-live.png"), fullPage: true });
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
