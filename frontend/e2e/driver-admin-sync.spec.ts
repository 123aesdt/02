import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Route } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

const now = "2026-09-16T10:00:00Z";
const screenshotDir = process.env.E2E_SYNC_SCREENSHOT_DIR
  ? path.resolve(process.env.E2E_SYNC_SCREENSHOT_DIR)
  : path.resolve(import.meta.dirname, "../.tmp/driver-admin-sync");

interface SharedApiState {
  reported: boolean;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json; charset=utf-8", body: JSON.stringify(body) });
}

function taskResult(taskId: string, incidentVehicleId: string, replacementVehicleId: string) {
  return {
    task_id: taskId,
    order_id: taskId === "TASK-LIVE-013" ? 13 : 1,
    ready: true,
    status: "COMPLETED",
    anomaly_type: "VEHICLE_BREAKDOWN",
    dispatch: {
      dispatch_id: taskId === "TASK-LIVE-013" ? 113 : 101,
      dispatch_no: taskId === "TASK-LIVE-013" ? "DSP-LIVE-013" : "DSP-BASE-001",
      original_route_id: "ROUTE-07",
      target_route_id: "ROUTE-10",
      status: "REROUTED",
      decision_reason: "替代车辆已自动匹配",
      fallback_used: false,
      fallback_reason: null,
      version: 1,
      executed: true,
    },
    audit: null,
    vehicle_allocation: {
      original_vehicle_id: incidentVehicleId,
      target_vehicle_id: replacementVehicleId,
      target_driver_id: "D-015",
      vehicle_reassigned: true,
      candidate_vehicles: [],
      pickup_route: null,
      scoring_formula: "FLEET_SCORE_V1",
    },
    route_plan: null,
    dispatch_impact: {
      incident_vehicle_id: incidentVehicleId,
      replacement_vehicle_id: replacementVehicleId,
      replacement_driver_id: "D-015",
      pickup_distance_km: "2.00",
      pickup_eta_minutes: 4,
      route_distance_delta_km: "-1.70",
      route_eta_delta_minutes: -2,
      total_distance_delta_km: "0.30",
      total_delay_minutes: 2,
      calculation_status: "CALCULATED",
    },
  };
}

async function installSharedApi(page: Page, state: SharedApiState) {
  await page.route("http://localhost:8001/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === "/api/v1/auth/demo-employees") return json(route, [
      { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" },
      { employee_id: "CF-DEMO-003", display_name: "王主管", role: "SUPERVISOR" },
    ]);
    if (url.pathname === "/api/v1/auth/demo-session") {
      const input = request.postDataJSON() as { employee_id: string };
      const supervisor = input.employee_id === "CF-DEMO-003";
      return json(route, {
        access_token: supervisor ? "sync-supervisor-token" : "sync-driver-token",
        token_type: "bearer",
        expires_in: 3600,
        principal: {
          subject_id: supervisor ? "supervisor-sync-003" : "driver-sync-001",
          display_name: supervisor ? "王主管" : "张师傅",
          roles: [supervisor ? "SUPERVISOR" : "EMPLOYEE"],
          permissions: supervisor
            ? ["dispatch:read", "dispatch:review", "anomalies:read"]
            : ["dispatch:read", "anomalies:report"],
          auth_method: "development_jwt",
          issued_at: now,
          expires_at: "2099-09-16T11:00:00Z",
        },
      });
    }
    if (url.pathname === "/api/v1/my/tasks") return json(route, {
      items: [{
        row_id: 13,
        task_id: "DEMO-TASK-REPORT-VEHICLE-013",
        order_no: "ORD-013",
        risk: "MEDIUM",
        description: "云和县生鲜配送",
        vehicle_id: "V-013",
        original_route_id: "ROUTE-07",
        suggested_route_id: null,
        status: "RUNNING",
        created_at: now,
        updated_at: now,
        origin: "县域中心仓",
        destination: "城东配送站",
        publication_status: "PENDING",
        published_at: null,
        route_instruction: null,
        can_report_anomaly: true,
      }],
      summary: { total: 1, ready: 0, waiting: 0, active: 1, ended: 0 },
      total: 1,
      next_cursor: null,
      provenance: "LIVE",
    });
    if (url.pathname === "/api/v1/anomaly-reports" && request.method() === "POST") {
      state.reported = true;
      return json(route, {
        anomaly_id: 13,
        anomaly_no: "ANOM-LIVE-013",
        task_id: "TASK-LIVE-013",
        accepted: true,
        duplicate: false,
        retryable: false,
        message: "问题已保存，AI 调度已启动。",
      }, 202);
    }
    if (url.pathname === "/api/v1/anomalies") {
      const items = [
        ...(state.reported ? [{
          row_id: 13,
          anomaly_no: "ANOM-LIVE-013",
          order_no: "ORD-013",
          driver_id: "D-013",
          vehicle_id: "V-013",
          route_id: "ROUTE-07",
          latest_task_id: "TASK-LIVE-013",
          anomaly_type: "VEHICLE_BREAKDOWN",
          risk: "HIGH",
          description: "司机上报制动系统故障，车辆无法继续行驶",
          status: "PENDING",
          reported_at: now,
        }] : []),
        {
          row_id: 1,
          anomaly_no: "ANOM-BASE-001",
          order_no: "ORD-001",
          driver_id: "D-001",
          vehicle_id: "V-001",
          route_id: "ROUTE-01",
          latest_task_id: "TASK-BASE-001",
          anomaly_type: "VEHICLE_BREAKDOWN",
          risk: "HIGH",
          description: "历史车辆故障",
          status: "COMPLETED",
          reported_at: "2026-09-15T08:00:00Z",
        },
      ];
      return json(route, { items, total: items.length, next_cursor: null, provenance: "LIVE" });
    }
    const resultMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)\/result$/);
    if (resultMatch) {
      return json(route, resultMatch[1] === "TASK-LIVE-013"
        ? taskResult("TASK-LIVE-013", "V-013", "V-015")
        : taskResult("TASK-BASE-001", "V-001", "V-005"));
    }
    const statusMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)$/);
    if (statusMatch) return json(route, {
      task_id: statusMatch[1],
      order_id: statusMatch[1] === "TASK-LIVE-013" ? 13 : 1,
      status: "COMPLETED",
      started_at: now,
      completed_at: now,
      created_at: now,
      ready: true,
      requires_manual_review: false,
    });
    if (url.pathname === "/api/v1/driver/operation-snapshot") {
      return json(route, { code: "OPERATION_PENDING", message: "处置记录生成中" }, 404);
    }
    if (url.pathname === "/api/v1/ws-tickets") {
      return json(route, { code: "SYNC_TEST_NO_SOCKET", message: "联动测试使用轮询" }, 503);
    }
    return json(route, { code: "NOT_MOCKED", message: `未模拟 ${url.pathname}` }, 404);
  });
}

test("司机上报后管理端在一秒轮询内提醒并自动定位故障车辆", async ({ browser }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  const sharedState: SharedApiState = { reported: false };
  const supervisorContext = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const driverContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const supervisorPage = await supervisorContext.newPage();
  const driverPage = await driverContext.newPage();
  await installSharedApi(supervisorPage, sharedState);
  await installSharedApi(driverPage, sharedState);

  await authenticatePage(supervisorPage, "SUPERVISOR", "/fleet-live-map");
  await expect(supervisorPage.getByRole("heading", { name: "车辆态势地图", level: 1 })).toBeVisible();
  await expect(supervisorPage.locator('[data-live-driver-report]')).toHaveCount(0);

  await authenticatePage(driverPage, "EMPLOYEE", "/report-issue");
  await driverPage.getByLabel("演示异常场景").selectOption("VEHICLE_BREAKDOWN_N04");
  await driverPage.getByRole("button", { name: "提交问题并启动 AI 调度" }).click();
  const syncState = driverPage.locator('[data-driver-sync-state="ACCEPTED"]');
  await expect(syncState).toContainText("后端已接收");
  await expect(syncState).toContainText("AI 调度已启动");
  await expect(syncState).toContainText("管理端将在 1 秒内同步");
  await driverPage.screenshot({ path: path.join(screenshotDir, "driver-sync-confirmation.png"), fullPage: true });

  const liveAlert = supervisorPage.locator("[data-live-driver-report]");
  await expect(liveAlert).toContainText("司机问题已同步", { timeout: 2_500 });
  await expect(liveAlert).toContainText("D-013");
  await expect(liveAlert).toContainText("V-013");
  await expect(supervisorPage.getByLabel("选择地图任务")).toHaveValue("TASK-LIVE-013");
  await expect(supervisorPage.locator('[data-fleet-vehicle-detail="V-013"]')).toBeVisible();
  await expect(supervisorPage.getByRole("button", { name: "停止跟随车辆" })).toHaveAttribute("aria-pressed", "true");
  await supervisorPage.screenshot({ path: path.join(screenshotDir, "admin-live-alert-and-vehicle.png"), fullPage: true });

  await supervisorPage.getByRole("button", { name: "关闭司机上报提醒" }).click();
  await expect(liveAlert).toHaveCount(0);
  await expect(supervisorPage.locator('[data-fleet-vehicle-detail="V-013"]')).toBeVisible();
  await expect(supervisorPage.getByRole("button", { name: "停止跟随车辆" })).toHaveAttribute("aria-pressed", "true");

  await supervisorPage.getByRole("button", { name: "关闭车辆运行详情" }).click();
  await supervisorPage.getByRole("button", { name: "历史轨迹" }).click();
  const vehicleMarkerSelector = ".amap-fleet-vehicle[data-vehicle-id], [data-fleet-vehicle-id]";
  const vehicleIds = await supervisorPage.locator(vehicleMarkerSelector).evaluateAll((nodes) => (
    nodes.map((node) => node.getAttribute("data-vehicle-id") ?? node.getAttribute("data-fleet-vehicle-id"))
      .filter((value): value is string => Boolean(value))
  ));
  expect(vehicleIds).toHaveLength(20);
  for (const vehicleId of vehicleIds) {
    await supervisorPage.locator(`.amap-fleet-vehicle[data-vehicle-id="${vehicleId}"], [data-fleet-vehicle-id="${vehicleId}"]`).click();
    await expect(supervisorPage.locator(`[data-fleet-vehicle-detail="${vehicleId}"]`)).toBeVisible();
    await supervisorPage.getByRole("button", { name: "关闭车辆运行详情" }).click();
  }

  await supervisorContext.close();
  await driverContext.close();
});
