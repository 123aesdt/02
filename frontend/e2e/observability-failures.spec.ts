import { expect, test } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

test("API 模式显示监控不可用且不回退演示数据", async ({ page }) => {
  await page.route("**/api/v1/observability/**", (route) => route.fulfill({ status: 503, contentType: "application/json", body: '{"code":"OBSERVABILITY_UNAVAILABLE"}' }));
  await authenticatePage(page, "OPERATOR", "/monitor");
  await expect(page.getByText("监控暂不可用", { exact: true })).toBeVisible();
  await expect(page.getByText("演示数据", { exact: true })).toHaveCount(0);
});

test("明确显示缺少监控读取权限", async ({ page }) => {
  await page.route("**/api/v1/observability/**", (route) => route.fulfill({ status: 403, contentType: "application/json", body: '{"code":"OBSERVABILITY_FORBIDDEN"}' }));
  await authenticatePage(page, "OPERATOR", "/monitor");
  await expect(page.getByText("需要监控读取权限", { exact: true })).toBeVisible();
});
