import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const screenshotDir = path.resolve(import.meta.dirname, "../../docs/verification/agent-pipeline");

test("mock dispatch shows what every Agent did and expands routing evidence", async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.setViewportSize({ width: 1470, height: 1000 });
  await page.goto("/dispatch/TASK-20260821-0042");

  const pipeline = page.locator(".pipeline-panel", {
    has: page.getByRole("heading", { name: "智能体流水线" }),
  });
  await expect(pipeline.locator(".pipeline-item")).toHaveCount(8);
  await expect(pipeline).toContainText("接入智能体");
  await expect(pipeline).toContainText("审核智能体");
  await expect(pipeline).not.toContainText('{"recommended_route"');
  await pipeline.screenshot({ path: path.join(screenshotDir, "agent-pipeline-collapsed.png") });

  const routingToggle = pipeline.getByRole("button", { name: "查看路径智能体工作详情" });
  await routingToggle.click();
  await expect(pipeline.getByRole("button", { name: "收起路径智能体工作详情" })).toHaveAttribute("aria-expanded", "true");
  await expect(pipeline).toContainText("读取信息");
  await expect(pipeline).toContainText("执行动作");
  await expect(pipeline).toContainText("输出结果");
  await expect(pipeline).toContainText("关键证据");
  await expect(pipeline).toContainText("比较 3 条候选路线，推荐 102 国道");
  await expect(pipeline).toContainText("demo-routing-06");
  await expect(pipeline.locator(".pipeline-work-detail")).toHaveCount(1);
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(errors).toEqual([]);

  await pipeline.screenshot({ path: path.join(screenshotDir, "agent-pipeline-expanded.png") });
});
