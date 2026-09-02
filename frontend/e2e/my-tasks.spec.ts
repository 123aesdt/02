import { expect, test } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

test("delivery employee sees only the server-owned task queue and can filter it", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });

  await authenticatePage(page, "EMPLOYEE", "/my-tasks");

  await expect(page.locator(".role-workspace").getByRole("heading", { name: "我的任务", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "任务概览" })).toBeVisible();
  await expect(page.getByText("DEMO-TASK-010", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "查看详情" }).first()).toHaveAttribute("href", /\/dispatch\/DEMO-TASK-/);
  await expect(page.getByText("演示数据", { exact: true })).toBeVisible();

  const readyResponse = page.waitForResponse((response) => response.url().includes("/api/v1/my/tasks") && response.url().includes("state=READY"));
  await page.getByRole("button", { name: "待执行", exact: true }).click();
  await expect((await readyResponse).status()).toBe(200);
  await expect(page.getByRole("button", { name: "待执行", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("DEMO-TASK-010", { exact: true })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("my tasks remains usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticatePage(page, "EMPLOYEE", "/my-tasks");

  await expect(page.locator(".role-workspace").getByRole("heading", { name: "我的任务", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "已结束", exact: true })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
});
