import { expect, test, type Page } from "@playwright/test";

import { apiBaseUrl } from "./support/api";
import { authenticatePage, bearer } from "./support/security-auth";

const overridePayload = {
  idempotency_key: "security-browser-override",
  entity_type: "Vehicle",
  entity_id: "vehicle-001",
  field: "status",
  old_value: "NORMAL",
  new_value: "BROKEN",
  reason: "security browser permission probe",
  expected_version: 7,
  expected_next_node: "capacity",
};

async function navigateSpa(page: Page, targetPath: string) {
  await page.evaluate((pathName) => {
    window.history.pushState(null, "", pathName);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, targetPath);
  await expect(page).toHaveURL(new RegExp(targetPath + "$"));
}

test.beforeEach(() => {
  test.skip(!process.env.DEVELOPMENT_JWT_SECRET, "Docker development JWT secret is required");
});

test("Docker development offers preconfigured demo employee accounts", async ({ page }) => {
  await page.goto("/");
  const employeeSwitcher = page.getByRole("combobox", { name: "切换演示员工" });
  await expect(employeeSwitcher).toBeVisible();
  await expect(employeeSwitcher.locator("option")).toHaveCount(7);
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await expect(page.getByLabel("登录密码")).toHaveValue("CountyFlow@2026");
  await expect(page.getByLabel("登录密码")).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: "验证令牌" })).toHaveCount(0);
});

test("Demo employee can logout and choose another identity", async ({ page }) => {
  await authenticatePage(page, "DISPATCHER");
  await page.getByRole("button", { name: "退出" }).click();
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();

  const adminSession = page.waitForResponse((response) => (
    response.url().endsWith("/api/v1/auth/demo-session")
    && response.request().method() === "POST"
  ));
  await page.getByRole("combobox", { name: "切换演示员工" }).selectOption("CF-DEMO-005");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  expect((await adminSession).ok()).toBe(true);
  await expect(page.locator(".auth-session-banner")).toContainText("系统管理员");
  await expect(page.getByRole("link", { name: "系统总览", exact: true })).toBeVisible();
});

test("Dispatcher can dispatch but cannot access monitoring or bypass runtime override", async ({ page, request }) => {
  const token = await authenticatePage(page, "DISPATCHER");
  await page.getByRole("link", { name: "智能调度", exact: true }).click();
  await expect(page.getByRole("heading", { name: "智能调度" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "系统监控", exact: true })).toHaveCount(0);
  await navigateSpa(page, "/monitor");
  await expect(page.getByRole("heading", { name: "无权访问" })).toBeVisible();
  const bypass = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/thread-missing/overrides`, { headers: bearer(token), data: overridePayload });
  expect(bypass.status()).toBe(403);
});

test("Supervisor has runtime and monitoring permission", async ({ page, request }) => {
  const token = await authenticatePage(page, "SUPERVISOR");
  await page.getByRole("link", { name: "系统监控", exact: true }).click();
  await expect(page.getByRole("heading", { name: "生产遥测", exact: true })).toBeVisible();
  const admitted = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/thread-missing/overrides`, { headers: bearer(token), data: overridePayload });
  expect(admitted.status()).not.toBe(403);
});

test("Operator can monitor but cannot read or mutate memory", async ({ page }) => {
  await authenticatePage(page, "OPERATOR");
  await page.getByRole("link", { name: "系统监控", exact: true }).click();
  await expect(page.getByRole("heading", { name: "生产遥测", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "记忆中心", exact: true })).toHaveCount(0);
  await navigateSpa(page, "/memory");
  await expect(page.getByRole("heading", { name: "无权访问" })).toBeVisible();
});

test("Auditor can inspect memory but cannot submit dispatch", async ({ page }) => {
  await authenticatePage(page, "AUDITOR");
  await page.getByRole("link", { name: "记忆中心", exact: true }).click();
  await expect(page.getByRole("tab", { name: "向量记忆" })).toBeVisible();
  await expect(page.getByRole("link", { name: "智能调度", exact: true })).toHaveCount(0);
  await navigateSpa(page, "/dispatch");
  await expect(page.getByRole("heading", { name: "无权访问" })).toBeVisible();
});

test("Admin can reach all protected workspaces", async ({ page }) => {
  await authenticatePage(page, "ADMIN");
  for (const label of ["智能调度", "智能体中心", "记忆中心", "系统监控"]) {
    const link = page.getByRole("link", { name: label, exact: true });
    await link.click();
    await expect(link).toHaveClass(/active/);
    await expect(page.getByRole("heading", { name: "无权访问" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "需要登录" })).toHaveCount(0);
  }
});
