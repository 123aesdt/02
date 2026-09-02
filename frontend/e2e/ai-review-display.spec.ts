import { randomUUID } from "node:crypto";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { apiBaseUrl } from "./support/api";
import { authenticatePage, bearer } from "./support/security-auth";

test.beforeEach(() => {
  test.skip(!process.env.DEVELOPMENT_JWT_SECRET, "Docker development JWT secret is required");
});

test("a tire report renders an 8-Agent action without a fabricated route", async ({ page, request }) => {
  await authenticatePage(page, "EMPLOYEE", "/my-tasks");
  const reportLink = page.getByRole("link", { name: "报告问题" }).first();
  await expect(reportLink).toBeVisible();
  await reportLink.click();

  await page.getByLabel("问题类型").selectOption("VEHICLE_BREAKDOWN");
  await page.getByLabel("当前位置").fill("新平路南段安全停车区");
  await page.getByLabel("问题描述").fill("右后轮爆胎，车辆无法继续安全行驶，请安排换胎或道路救援。");
  await page.getByLabel("车辆状态").selectOption("BROKEN");
  await page.getByLabel("风险等级").selectOption("HIGH");

  const acceptedResponse = page.waitForResponse((response) => (
    response.url().endsWith("/api/v1/anomaly-reports")
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "提交问题并启动 AI 调度" }).click();
  const accepted = await (await acceptedResponse).json() as { task_id: string };
  expect(accepted.task_id).toMatch(/^TASK-/);

  const supervisorToken = await authenticatePage(page, "SUPERVISOR", "/reviews");
  await expect.poll(async () => {
    const response = await request.get(`${apiBaseUrl}/api/v1/reviews?limit=20`, {
      headers: bearer(supervisorToken),
    });
    const payload = await response.json() as {
      items: { task_id: string; ai_recommended_action: string | null }[];
    };
    return payload.items.find((item) => item.task_id === accepted.task_id)?.ai_recommended_action ?? "";
  }, { timeout: 45_000 }).toContain("更换轮胎");

  await authenticatePage(page, "SUPERVISOR", "/reviews");
  await expect(page).toHaveURL(/\/reviews$/);

  const row = page.locator("tr", { hasText: accepted.task_id });
  await expect(row).toBeVisible();
  await expect(row).toContainText("当前不适用");
  await expect(row).toContainText("8-Agent 分析完成");
  await expect(page.getByText("AI 分析原因", { exact: true })).toBeVisible();
  await expect(page.getByText("AI 处置建议", { exact: true })).toBeVisible();

  const screenshotRoot = process.env.TEMP ?? process.env.TMP ?? ".";
  await page.screenshot({
    path: path.join(screenshotRoot, `countyflow-ai-review-${randomUUID()}.png`),
    fullPage: true,
  });
});
