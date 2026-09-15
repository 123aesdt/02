import { randomUUID } from "node:crypto";

import { expect, test } from "@playwright/test";

import { apiBaseUrl } from "./support/api";
import { authenticatePage, bearer } from "./support/security-auth";

test.beforeEach(() => {
  test.skip(!process.env.DEVELOPMENT_JWT_SECRET, "Docker development JWT secret is required");
});

test("employee route map matches fleet dispatch without showing repair before a report", async ({ page }) => {
  const operationRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/driver/operation-snapshot")) {
      operationRequests.push(request.url());
    }
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await authenticatePage(page, "EMPLOYEE", "/report-issue");
  await expect(page.locator("select#report-vehicle")).toHaveCount(0);
  await expect(page.getByLabel("固定车辆")).toHaveValue("车辆-002");

  const map = page.locator('[data-driver-route-map][data-route-id="ROUTE-01"]');
  await expect(map).toHaveAttribute("data-map-contract", "AMAP_ROAD_V1");
  await expect(map).toHaveAttribute("data-route-node-ids", "N19,N01,N03,N22,N20,N05,N06");
  await expect(map).toHaveAttribute("data-current-vehicle-id", "V-002");
  await expect(map).toHaveAttribute("data-map-provider", "AMAP");

  const stage = map.locator(".fleet-amap-stage");
  await expect(stage).toHaveAttribute("data-amap-state", "READY", { timeout: 20_000 });
  await expect(map.locator('[data-amap-node-id="N19"]')).toHaveCount(1);
  await expect(map.locator('[data-amap-node-id="N06"]')).toHaveCount(1);
  const vehicle = map.locator('[data-amap-route-id="ROUTE-01"]');
  await expect(vehicle).toHaveCount(1);
  await expect(stage).toHaveAttribute("data-road-planned-count", "1");
  await expect(page.locator("[data-driver-operation-status]")).toHaveCount(0);
  expect(operationRequests).toHaveLength(0);

  const firstLng = await vehicle.getAttribute("data-amap-lng");
  await expect.poll(async () => vehicle.getAttribute("data-amap-lng"), { timeout: 4_000 }).not.toBe(firstLng);

  const interactionLayer = map.locator(".amap-maps");
  await expect(interactionLayer).toBeVisible();
  await expect(interactionLayer).toHaveCSS("cursor", "grab");

  await page.screenshot({ path: "../.tmp/employee-amap-operation-unified.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
});

test("delivery employee reports an assigned task and receives one AI dispatch identity", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await authenticatePage(page, "EMPLOYEE", "/my-tasks");
  await expect(page.locator(".role-workspace__heading").getByRole("heading", { name: "我的任务", level: 1 })).toBeVisible();

  const reportLink = page.getByRole("link", { name: "报告问题" }).first();
  await expect(reportLink).toBeVisible();
  const href = await reportLink.getAttribute("href");
  const sourceTaskId = new URL(href ?? "", "http://countyflow.local").searchParams.get("taskId");
  expect(sourceTaskId).toBeTruthy();

  const anotherEmployeeSession = await request.post(`${apiBaseUrl}/api/v1/auth/demo-session`, {
    data: { employee_id: "CF-DEMO-006" },
  });
  expect(anotherEmployeeSession.status()).toBe(200);
  const anotherEmployeeToken = (await anotherEmployeeSession.json() as { access_token: string }).access_token;
  const forbidden = await request.post(`${apiBaseUrl}/api/v1/anomaly-reports`, {
    headers: bearer(anotherEmployeeToken),
    data: {
      source_task_id: sourceTaskId,
      anomaly_type: "ROAD_HAZARD",
      description: "跨员工归属边界验证，不应创建异常任务。",
      location_text: "新平路边界测试点",
      reported_vehicle_status: "NORMAL",
      severity: "MEDIUM",
      idempotency_key: `e2e-forbidden-${randomUUID()}`,
    },
  });
  expect(forbidden.status()).toBe(403);
  expect((await forbidden.json() as { code: string }).code).toBe("REPORT_SOURCE_FORBIDDEN");

  await reportLink.click();
  await expect(page).toHaveURL(/\/report-issue\?taskId=/);
  await expect(page.locator(".role-workspace__heading").getByRole("heading", { name: "提出配送问题", level: 1 })).toBeVisible();
  await page.getByLabel("问题类型").selectOption("ROAD_HAZARD");
  await page.getByLabel("问题描述").fill("连续降雨导致路面明显湿滑，请立即重新评估安全路线。");
  await page.getByLabel("车辆状态").selectOption("NORMAL");
  await page.getByLabel("风险等级").selectOption("HIGH");

  const acceptedResponse = page.waitForResponse((response) => (
    response.url().endsWith("/api/v1/anomaly-reports")
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "提交问题并启动 AI 调度" }).click();
  const response = await acceptedResponse;
  expect(response.status()).toBe(202);
  const accepted = await response.json() as { anomaly_no: string; task_id: string; duplicate: boolean };
  expect(accepted.anomaly_no).toMatch(/^ANOM-/);
  expect(accepted.task_id).toMatch(/^TASK-/);
  expect(accepted.duplicate).toBe(false);
  const success = page.locator(".report-feedback--success");
  await expect(success).toContainText(/异常-\d{3}/);
  await expect(success).toContainText(/调度任务-\d{3}/);
  await expect(page.getByRole("link", { name: "查看 AI 调度进度" })).toHaveAttribute("href", `/dispatch/${accepted.task_id}`);

  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
});
