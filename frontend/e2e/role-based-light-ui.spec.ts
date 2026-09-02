import fs from "node:fs";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { Role } from "../src/auth/permissions";
import { apiBaseUrl, createRuntimeTask, waitForEligibility, waitForTaskReady } from "./support/api";
import { pauseWorkerOne, pauseWorkerTwo, unpauseWorkerOne, unpauseWorkerTwo } from "./support/docker";
import { openOverrideDialog } from "./support/runtime-task";

const screenshotDir = path.resolve(import.meta.dirname, "../../docs/verification/frontend-role-ui/screenshots");

interface DevelopmentSession {
  access_token: string;
  principal: { roles: Role[]; permissions: string[]; display_name: string };
}

const landing: Record<Role, string> = {
  EMPLOYEE: "/my-tasks",
  DISPATCHER: "/workspace",
  SUPERVISOR: "/supervisor",
  OPERATOR: "/operations",
  AUDITOR: "/audit",
  ADMIN: "/overview",
};

async function switchRole(page: Page, role: Role): Promise<DevelopmentSession> {
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/auth/development-session")
      && response.request().method() === "POST",
  );
  const preview = page.getByLabel("DEV AUTH 角色预览");
  await expect(preview).toBeEnabled();
  await preview.selectOption(role);
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const session = await response.json() as DevelopmentSession;
  expect(session.principal.roles).toEqual([role]);
  await expect(page).toHaveURL(new RegExp(`${landing[role]}$`));
  return session;
}

async function background(page: Page, selector: string): Promise<string> {
  return page.locator(selector).first().evaluate((node) => getComputedStyle(node).backgroundColor);
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function navigateSpa(page: Page, targetPath: string) {
  await page.evaluate((pathName) => {
    window.history.pushState(null, "", pathName);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, targetPath);
  await expect(page).toHaveURL(new RegExp(`${targetPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`));
}

async function assertCoreLightSurfaces(page: Page) {
  expect(await background(page, "body")).toBe("rgb(255, 255, 255)");
  expect(await background(page, ".app-shell")).toBe("rgb(255, 255, 255)");
  expect(await background(page, ".sidebar")).toBe("rgb(255, 255, 255)");
  expect(await background(page, ".topbar")).toBe("rgb(255, 255, 255)");
}

async function directRoleSession(request: APIRequestContext, role: Role): Promise<DevelopmentSession> {
  const response = await request.post(`${apiBaseUrl}/api/v1/auth/development-session`, { data: { role } });
  expect(response.status()).toBe(200);
  const session = await response.json() as DevelopmentSession;
  expect(session.principal.roles).toEqual([role]);
  return session;
}

test("five role workspaces use server-issued identities and a complete light UI", async ({ page, request }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByLabel("DEV AUTH 角色预览")).toBeVisible();
  await assertCoreLightSurfaces(page);
  await page.screenshot({ path: path.join(screenshotDir, "role-preview-dev.png"), fullPage: true });

  const escalation = await request.post(`${apiBaseUrl}/api/v1/auth/development-session`, {
    data: { role: "DISPATCHER", permissions: ["system:admin"] },
  });
  expect(escalation.status()).toBe(422);

  const dispatcher = await switchRole(page, "DISPATCHER");
  await expect(page.locator(".page-content").getByRole("heading", { name: "调度工作台" })).toBeVisible();
  await expect(page.getByRole("link", { name: "异常中心", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "智能调度", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "运单管理", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "系统监控", exact: true })).toHaveCount(0);
  await expect(page.getByText("Runtime Intervention", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, "dispatcher-workspace.png"), fullPage: true });

  await navigateSpa(page, "/anomalies");
  await expect(page.getByText("异常列表接口尚未开放")).toBeVisible();
  await expect(page.getByText("当前异常", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, "dispatcher-anomaly.png"), fullPage: true });

  await navigateSpa(page, "/dispatch");
  await expect(page.getByRole("heading", { name: "异常调度任务" })).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "dispatcher-dispatch.png"), fullPage: true });

  const dispatcherOverride = await request.post(`${apiBaseUrl}/api/v1/runtime/threads/not-a-thread/overrides`, {
    headers: { Authorization: `Bearer ${dispatcher.access_token}` },
    data: {
      idempotency_key: "dispatcher-must-not-override",
      entity_type: "Vehicle",
      entity_id: "vehicle-001",
      field: "status",
      old_value: "NORMAL",
      new_value: "BROKEN",
      reason: "permission boundary verification",
      expected_version: 1,
      expected_next_node: "capacity",
    },
  });
  expect(dispatcherOverride.status()).toBe(403);

  const supervisor = await switchRole(page, "SUPERVISOR");
  process.env.E2E_ACCESS_TOKEN = supervisor.access_token;
  await expect(page.locator(".page-content").getByRole("heading", { name: "调度主管台" })).toBeVisible();
  await expect(page.getByText("待人工复核", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("全局干预任务列表接口尚未开放")).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, "supervisor-workspace.png"), fullPage: true });

  let workerOnePaused = false;
  let workerTwoStopped = false;
  let runtimeTaskId: string;
  try {
    pauseWorkerTwo();
    workerTwoStopped = true;
    runtimeTaskId = await createRuntimeTask(request);
    await waitForEligibility(request, runtimeTaskId, "ELIGIBLE");
    pauseWorkerOne();
    workerOnePaused = true;

    await navigateSpa(page, `/dispatch/${encodeURIComponent(runtimeTaskId)}`);
    const dialog = await openOverrideDialog(page, runtimeTaskId, "BROKEN");
    expect(await background(page, ".runtime-override-dialog")).toBe("rgb(255, 255, 255)");
    await dialog.getByLabel("Reason").fill("人工确认车辆爆胎，执行主管安全干预");
    await page.screenshot({ path: path.join(screenshotDir, "supervisor-intervention.png") });
    await dialog.getByRole("button", { name: "确认干预" }).click();
    await expect(page.locator('[data-submission-state="APPLIED"]')).toBeVisible();

    unpauseWorkerOne();
    workerOnePaused = false;
    unpauseWorkerTwo();
    workerTwoStopped = false;
    await waitForTaskReady(request, runtimeTaskId);
  } finally {
    if (workerOnePaused) try { unpauseWorkerOne(); } catch { /* restore worker */ }
    if (workerTwoStopped) try { unpauseWorkerTwo(); } catch { /* restore worker */ }
  }

  await switchRole(page, "OPERATOR");
  await expect(page.locator(".page-content").getByRole("heading", { name: "运行中心" })).toBeVisible();
  await expect(page.getByText("System Health", { exact: true })).toBeVisible();
  await expect(page.getByText("发起智能调度", { exact: true })).toHaveCount(0);
  await expect(page.getByText("确认干预", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, "operator-operations.png"), fullPage: true });

  await switchRole(page, "AUDITOR");
  await expect(page.locator(".page-content").getByRole("heading", { name: "审计中心" })).toBeVisible();
  await expect(page.getByText("安全审计时间线")).toBeVisible();
  await expect(page.getByRole("status", { name: "正在读取安全审计事件" })).toHaveCount(0);
  await expect(page.locator(".ui-data-table tbody tr").first()).toBeVisible();
  await expect(page.locator(".page-content button")).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, "auditor-audit.png"), fullPage: true });

  await switchRole(page, "ADMIN");
  await expect(page.locator(".page-content").getByRole("heading", { name: "系统总览" })).toBeVisible();
  await expect(page.getByRole("link", { name: "治理与安全" })).toBeVisible();
  await expect(page.getByText(/IAM|用户管理|租户管理/)).toHaveCount(0);
  await page.screenshot({ path: path.join(screenshotDir, "admin-overview.png"), fullPage: true });

  await navigateSpa(page, "/memory");
  await expect(page.getByRole("tab", { name: "Vector Memory" })).toHaveAttribute("aria-selected", "true");
  await page.screenshot({ path: path.join(screenshotDir, "memory-light.png"), fullPage: true });
  await page.getByRole("tab", { name: "Graph Memory" }).click();
  await page.getByLabel("Task ID").fill(runtimeTaskId);
  await expect(page.getByRole("img", { name: "Graph Memory entity relationships" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Path Inspector" })).toBeVisible();
  expect(["rgb(246, 248, 250)", "rgb(255, 255, 255)"]).toContain(await background(page, ".graph-canvas"));
  expect(await background(page, ".graph-property-inspector")).toBe("rgb(255, 255, 255)");
  await page.screenshot({ path: path.join(screenshotDir, "graph-light.png"), fullPage: true });

  await navigateSpa(page, "/monitor");
  const monitoringState = page.locator(".live-observability-panel .source-label");
  await expect(monitoringState).toHaveText(/LIVE|STALE/);
  if (await monitoringState.textContent() === "STALE") {
    await expect(page.getByText("Live telemetry is stale; last safe samples are shown.")).toBeVisible();
  }
  expect(await background(page, ".live-observability-panel")).toBe("rgb(255, 255, 255)");
  await page.screenshot({ path: path.join(screenshotDir, "monitoring-light.png"), fullPage: true });

  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    await page.reload();
    await assertCoreLightSurfaces(page);
    await expectNoHorizontalOverflow(page);
  }

  const adminSession = await directRoleSession(request, "ADMIN");
  expect(adminSession.principal.permissions).toContain("system:admin");
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
  expect(fs.readdirSync(screenshotDir).filter((name) => name.endsWith(".png"))).toEqual(expect.arrayContaining([
    "dispatcher-workspace.png", "dispatcher-anomaly.png", "dispatcher-dispatch.png",
    "supervisor-workspace.png", "supervisor-intervention.png", "operator-operations.png",
    "auditor-audit.png", "admin-overview.png", "memory-light.png", "monitoring-light.png",
    "graph-light.png", "role-preview-dev.png",
  ]));
});
