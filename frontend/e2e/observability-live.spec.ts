import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

test("live observability remains separate from VERIFIED ACCEPTANCE", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/monitor");
  await expect(page.getByText("LIVE OBSERVABILITY", { exact: true })).toBeVisible();
  await expect(page.getByText("VERIFIED ACCEPTANCE", { exact: true })).toBeVisible();
  await expect(page.locator(".live-observability-panel .source-label")).toHaveText(/LIVE|STALE/);
  await expect(page.getByText("DEMO DATA", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/MySQL (UP|DOWN)/)).toBeVisible();
  const screenshotDirectory = path.resolve(import.meta.dirname, "../../docs/verification/v2-g1/screenshots");
  fs.mkdirSync(screenshotDirectory, { recursive: true });
  await page.screenshot({ path: path.join(screenshotDirectory, "monitoring-live.png"), fullPage: true });
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
