import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

const screenshotPath = path.resolve("../docs/verification/screenshots/amap-published-driver-route.png");

test("道路阻断自动发布后，司机端显示可交互的高德真实道路路线", async ({ page }) => {
  test.setTimeout(120_000);
  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
  const browserErrors: string[] = [];
  const httpErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) {
      browserErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    const expectedEmptyOperationSnapshot = response.status() === 404
      && response.url().includes("/api/v1/driver/operation-snapshot");
    if (response.status() >= 400 && !expectedEmptyOperationSnapshot) {
      httpErrors.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await authenticatePage(page, "EMPLOYEE", "/report-issue");
  await page.getByLabel("演示异常场景").selectOption("ROAD_BLOCKED_E04");
  await expect(page.getByLabel("问题类型")).toHaveValue("ROAD_BLOCKED");
  await expect(page.getByLabel("当前位置")).toHaveValue("新平路东河桥段");

  const acceptedResponse = page.waitForResponse((response) => (
    response.url().endsWith("/api/v1/anomaly-reports")
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "提交问题并启动 AI 调度" }).click();
  const accepted = await acceptedResponse;
  expect(accepted.status()).toBe(202);
  const payload = await accepted.json() as { task_id: string };
  expect(payload.task_id).toMatch(/^TASK-/);

  await page.getByRole("link", { name: "查看 AI 调度进度" }).click();
  await expect(page).toHaveURL(new RegExp(`/dispatch/${payload.task_id}$`));
  await expect(page.getByRole("heading", { name: "调度路线已发布" })).toBeVisible({ timeout: 60_000 });

  const routeMap = page.locator(".published-route-map");
  await expect(routeMap).toBeVisible();
  await expect(routeMap).toHaveAttribute("data-published-route-state", "READY", { timeout: 30_000 });
  await expect(routeMap).toContainText("高德道路已匹配");
  await expect(routeMap).toContainText("司机端实时匹配");
  await expect(routeMap).toContainText("调度行驶说明");
  await expect(routeMap.locator(".published-route-facts strong")).toHaveCount(4);

  const interactiveMap = routeMap.locator(".amap-maps");
  await expect(interactiveMap).toBeVisible();
  await expect(interactiveMap).toHaveCSS("cursor", "grab");
  const box = await interactiveMap.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move((box?.x ?? 0) + 120, (box?.y ?? 0) + 120);
  await page.mouse.wheel(0, -220);
  await expect(routeMap).toHaveAttribute("data-published-route-state", "READY");

  await expect(page.getByText(/runtime:read/)).toHaveCount(0);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
  expect(httpErrors).toEqual([]);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
});
