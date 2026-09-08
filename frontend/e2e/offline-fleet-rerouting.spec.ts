import fs from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Route } from "@playwright/test";

import { authenticatePage } from "./support/security-auth";

const screenshotDir = path.resolve(import.meta.dirname, "../../docs/verification/fleet-rerouting/screenshots");
const now = "2026-09-07T08:00:00Z";

const taskByAnomaly = {
  VEHICLE_BREAKDOWN: "TASK-OFFLINE-BREAKDOWN-001",
  ROAD_BLOCKED: "TASK-OFFLINE-ROAD-BLOCKED-005",
} as const;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json; charset=utf-8", body: JSON.stringify(body) });
}

function pathEvidence(edgeIds: string[], distanceKm: string, minutes: number) {
  return {
    objective: "TRAVEL_TIME",
    node_ids: edgeIds.map((_, index) => `N${String(index + 1).padStart(2, "0")}`).concat("N06"),
    edge_ids: edgeIds,
    distance_km: distanceKm,
    estimated_minutes: minutes,
    risk_cost: "0.00",
    visited_node_count: 8,
    scoring_formula: "DIJKSTRA_TRAVEL_TIME_V1",
  };
}

function networkNodes() {
  return Array.from({ length: 18 }, (_, index) => ({
    node_id: `N${String(index + 1).padStart(2, "0")}`,
    name: index === 0 ? "新平县中心仓" : index === 5 ? "城东配送站" : `县域节点 ${index + 1}`,
    x_km: String((index % 6) * 2),
    y_km: String(Math.floor(index / 6) * 3),
    node_type: index === 0 || index === 5 ? "STATION" : "JUNCTION",
  }));
}

function networkEdges() {
  const primary = [
    ["N01", "N02"], ["N02", "N03"], ["N03", "N04"], ["N04", "N05"], ["N05", "N06"],
    ["N02", "N07"], ["N07", "N08"], ["N08", "N09"], ["N09", "N06"],
  ];
  return Array.from({ length: 26 }, (_, index) => {
    const edgeId = `E${String(index + 1).padStart(2, "0")}`;
    const [from, to] = primary[index] ?? [
      `N${String((index % 17) + 1).padStart(2, "0")}`,
      `N${String((index % 17) + 2).padStart(2, "0")}`,
    ];
    return {
      edge_id: edgeId,
      name: edgeId === "E04" ? "新平路东河桥段" : edgeId === "E07" ? "102 国道西段" : `县域道路 ${edgeId}`,
      from_node_id: from,
      to_node_id: to,
      distance_km: edgeId === "E04" ? "2.50" : "1.50",
      base_minutes: edgeId === "E04" ? 5 : 3,
      road_level: edgeId === "E07" ? "NATIONAL" : "COUNTY",
      risk_level: edgeId === "E04" ? "HIGH" : "LOW",
      status: edgeId === "E04" ? "BLOCKED" : "OPEN",
      congestion_factor: "1.00",
      weight_limit_tons: "8.00",
      bidirectional: true,
      version: 7,
    };
  });
}

function scoreComponents() {
  return {
    eta_penalty: "-3.0",
    distance_penalty: "-1.4",
    load_penalty: "-2.2",
    road_risk_penalty: "0.0",
    same_station_bonus: "0.0",
    cargo_exact_match_bonus: "0.0",
  };
}

function fleetCandidates() {
  return Array.from({ length: 12 }, (_, index) => {
    const number = index + 1;
    const vehicleId = `V-${String(number).padStart(3, "0")}`;
    const selected = vehicleId === "V-005";
    const original = vehicleId === "V-001";
    return {
      vehicle_id: vehicleId,
      driver_id: selected ? "D-003" : `D-${String(number).padStart(3, "0")}`,
      vehicle_status: original ? "BROKEN" : "AVAILABLE",
      driver_status: "AVAILABLE",
      remaining_capacity_kg: selected ? "1300.00" : "900.00",
      gross_weight_tons: "3.50",
      cargo_capability: selected ? "COLD_CHAIN" : "GENERAL",
      pickup_route: selected ? pathEvidence(["E20"], "2.80", 6) : null,
      pickup_distance_km: selected ? "2.80" : null,
      pickup_eta_minutes: selected ? 6 : null,
      score: selected ? "93.4" : original ? null : "80.0",
      score_components: selected ? scoreComponents() : null,
      scoring_formula: "100-ETA-DISTANCE-LOAD-RISK+BONUS",
      eligible: !original,
      exclusion_reasons: original ? ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"] : [],
    };
  });
}

function baseResult(taskId: string, orderId: number) {
  return {
    task_id: taskId,
    order_id: orderId,
    ready: true,
    status: "COMPLETED",
    dispatch: {
      dispatch_id: orderId + 100,
      dispatch_no: `DSP-${orderId}`,
      original_route_id: "RTE-NEWPING",
      target_route_id: "RTE-OFFLINE-RESULT",
      status: "REROUTED",
      decision_reason: "离线县域沙盘完成确定性计算",
      fallback_used: false,
      fallback_reason: null,
      version: 1,
      executed: true,
    },
    audit: { result: "APPROVED", reason: "证据完整", dispatch_id: orderId + 100, created_at: now },
    publication: null,
  };
}

function breakdownResult() {
  return {
    ...baseResult(taskByAnomaly.VEHICLE_BREAKDOWN, 1),
    vehicle_allocation: {
      original_vehicle_id: "V-001",
      target_vehicle_id: "V-005",
      target_driver_id: "D-003",
      vehicle_reassigned: true,
      candidate_vehicles: fleetCandidates(),
      pickup_route: pathEvidence(["E20"], "2.80", 6),
      scoring_formula: "100-ETA-DISTANCE-LOAD-RISK+BONUS",
    },
    route_plan: null,
  };
}

function blockedResult() {
  return {
    ...baseResult(taskByAnomaly.ROAD_BLOCKED, 5),
    vehicle_allocation: null,
    route_plan: {
      original_path: pathEvidence(["E01", "E02", "E03", "E04", "E05"], "10.00", 20),
      recommended_path: pathEvidence(["E01", "E06", "E07", "E08", "E09"], "13.20", 24),
      candidate_routes: [{
        route_id: "RTE-DET-001",
        route_name: "102 国道绕行方案",
        objective: "TRAVEL_TIME",
        node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"],
        edge_ids: ["E01", "E06", "E07", "E08", "E09"],
        distance_km: "13.20",
        estimated_minutes: 24,
        risk_level: "LOW",
        risk_cost: "0.00",
        visited_node_count: 8,
        available: true,
        reason: "避开堵塞边 E04",
        score: "88.0",
        score_components: null,
        scoring_formula: "ROUTE_SCORE_V1",
        algorithm_version: "DIJKSTRA_V1",
        road_network_version: 7,
      }],
      blocked_edge_ids: ["E04"],
      distance_delta_km: "3.20",
      eta_delta_minutes: 4,
      visited_node_count: 8,
      routing_status: "REROUTED",
      algorithm: "DIJKSTRA_V1",
      road_network_version: 7,
      network_nodes: networkNodes(),
      network_edges: networkEdges(),
    },
  };
}

async function installOfflineApi(page: Page) {
  await page.route("http://localhost:8001/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/health") return json(route, { status: "ok" });
    if (url.pathname === "/api/v1/auth/demo-employees") return json(route, [{ employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" }]);
    if (url.pathname === "/api/v1/auth/demo-session") return json(route, {
      access_token: "offline-ui-regression-token",
      token_type: "bearer",
      expires_in: 3600,
      principal: {
        subject_id: "employee-offline-001",
        display_name: "张师傅",
        roles: ["EMPLOYEE"],
        permissions: ["dispatch:read", "anomalies:report"],
        auth_method: "development_jwt",
        issued_at: now,
        expires_at: "2099-09-07T09:00:00Z",
      },
    });
    if (url.pathname === "/api/v1/my/tasks") return json(route, {
      items: [
        { row_id: 1, task_id: "SOURCE-DEMO-001", order_no: "DEMO-ORDER-001", risk: "HIGH", description: "车辆故障演示任务", vehicle_id: "V-001", original_route_id: "RTE-NEWPING", suggested_route_id: null, status: "RUNNING", created_at: now, updated_at: now, origin: "新平县中心仓", destination: "城东配送站", publication_status: "PENDING", published_at: null, route_instruction: null },
        { row_id: 5, task_id: "SOURCE-DEMO-005", order_no: "DEMO-ORDER-005", risk: "HIGH", description: "道路阻断演示任务", vehicle_id: "V-008", original_route_id: "RTE-NEWPING", suggested_route_id: null, status: "RUNNING", created_at: now, updated_at: now, origin: "新平县中心仓", destination: "城东配送站", publication_status: "PENDING", published_at: null, route_instruction: null },
      ],
      summary: { total: 2, ready: 0, waiting: 0, active: 2, ended: 0 },
      total: 2,
      next_cursor: null,
      provenance: "DEMO",
    });
    if (url.pathname === "/api/v1/anomaly-reports" && request.method() === "POST") {
      const input = request.postDataJSON() as { anomaly_type: keyof typeof taskByAnomaly };
      const taskId = taskByAnomaly[input.anomaly_type];
      return json(route, { anomaly_id: input.anomaly_type === "VEHICLE_BREAKDOWN" ? 101 : 105, anomaly_no: input.anomaly_type === "VEHICLE_BREAKDOWN" ? "ANOM-OFFLINE-001" : "ANOM-OFFLINE-005", task_id: taskId, accepted: true, duplicate: false, retryable: false, message: "问题已保存，AI 调度已启动。" }, 202);
    }
    const resultMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)\/result$/);
    if (resultMatch) return json(route, resultMatch[1] === taskByAnomaly.VEHICLE_BREAKDOWN ? breakdownResult() : blockedResult());
    const statusMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)$/);
    if (statusMatch) return json(route, { task_id: statusMatch[1], order_id: statusMatch[1] === taskByAnomaly.VEHICLE_BREAKDOWN ? 1 : 5, status: "COMPLETED", started_at: now, completed_at: now, created_at: now, ready: true, requires_manual_review: false });
    if (url.pathname === "/api/v1/ws-tickets") return json(route, { code: "UI_REGRESSION_NO_SOCKET", message: "确定性 UI 回归不连接 WebSocket" }, 503);
    return json(route, { code: "NOT_MOCKED", message: `未模拟 ${url.pathname}` }, 404);
  });
}

async function submitVisibleIssue(page: Page, sourceTaskId: string, anomalyType: "VEHICLE_BREAKDOWN" | "ROAD_BLOCKED") {
  await page.evaluate((pathName) => {
    window.history.pushState(null, "", pathName);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, `/report-issue?taskId=${sourceTaskId}`);
  await expect(page.locator(".role-workspace__heading").getByRole("heading", { name: "提出配送问题", level: 1 })).toBeVisible();
  await page.getByLabel("问题类型").selectOption(anomalyType);
  await page.getByLabel("当前位置").fill(anomalyType === "VEHICLE_BREAKDOWN" ? "新平路 K3.2" : "新平路东河桥段 E04");
  await page.getByLabel("问题描述").fill(anomalyType === "VEHICLE_BREAKDOWN" ? "V-001 发动机故障，无法继续配送，请立即安排替代车辆。" : "E04 塌方完全阻断，请重新计算县域配送路线。" );
  await page.getByLabel("车辆状态").selectOption(anomalyType === "VEHICLE_BREAKDOWN" ? "BROKEN" : "NORMAL");
  await page.getByLabel("风险等级").selectOption("HIGH");
  const submitted = page.waitForResponse((response) => response.url().endsWith("/api/v1/anomaly-reports") && response.request().method() === "POST");
  await page.getByRole("button", { name: "提交问题并启动 AI 调度" }).click();
  expect((await submitted).status()).toBe(202);
  await page.getByRole("link", { name: "查看 AI 调度进度" }).click();
}

test.beforeEach(async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  await installOfflineApi(page);
  await authenticatePage(page, "EMPLOYEE", "/my-tasks");
});

test("网络拦截 UI 回归：车辆故障后展示其他车辆与司机调度，刷新后证据不变", async ({ page }) => {
  await submitVisibleIssue(page, "SOURCE-DEMO-001", "VEHICLE_BREAKDOWN");
  await expect(page.getByRole("heading", { name: "替代车辆调度计算" })).toBeVisible();
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-001");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-005");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("D-003");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("接驳 2.80 公里 · 6 分钟");
  await expect(page.locator(".fleet-score-summary")).toContainText("93.4");
  await expect(page.locator(".fleet-candidate-table tbody tr")).toHaveCount(12);
  await expect(page.getByLabel("V-001 候选车辆")).toContainText("原故障车辆不参与候选");
  await expect(page.getByLabel("V-006 候选车辆")).toContainText("满足硬约束");
  await page.reload();
  await expect(page.getByRole("heading", { name: "需要登录" })).toBeVisible();
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskByAnomaly.VEHICLE_BREAKDOWN}`);
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-001");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-005");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("D-003");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("接驳 2.80 公里 · 6 分钟");
  await expect(page.locator(".fleet-score-summary")).toContainText("93.4");
  await expect(page.locator(".fleet-candidate-table tbody tr")).toHaveCount(12);
  await expect(page.getByLabel("V-001 候选车辆")).toContainText("原故障车辆不参与候选");
  await expect(page.getByLabel("V-006 候选车辆")).toContainText("满足硬约束");
  await page.screenshot({ path: path.join(screenshotDir, "vehicle-breakdown-candidates.png"), fullPage: true });
});

test("网络拦截 UI 回归：道路堵塞后展示 Dijkstra 新路线，刷新后证据不变", async ({ page }) => {
  await submitVisibleIssue(page, "SOURCE-DEMO-005", "ROAD_BLOCKED");
  const panel = page.locator(".route-plan-result-panel");
  await expect(panel.getByRole("heading", { name: "新路线规划计算" })).toBeVisible();
  await expect(panel).toContainText("Dijkstra（DIJKSTRA_V1）");
  await expect(panel).toContainText("网络版本 7");
  await expect(panel).toContainText("E01 → E02 → E03 → E04 → E05");
  await expect(panel).toContainText("E01 → E06 → E07 → E08 → E09");
  await expect(panel).toContainText("+3.20 公里");
  await expect(panel).toContainText("+4 分钟");
  await expect(panel.locator('[data-edge-id="E04"]')).toHaveAttribute("data-route-state", "blocked");
  await expect(panel.locator('[data-edge-id="E07"]')).toHaveAttribute("data-route-state", "recommended");
  await expect(panel.locator(".network-node")).toHaveCount(18);
  await expect(panel.locator(".road-edge")).toHaveCount(26);
  await page.reload();
  await expect(page.getByRole("heading", { name: "需要登录" })).toBeVisible();
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskByAnomaly.ROAD_BLOCKED}`);
  await expect(panel).toContainText("Dijkstra（DIJKSTRA_V1）");
  await expect(panel).toContainText("网络版本 7");
  await expect(panel).toContainText("E01 → E02 → E03 → E04 → E05");
  await expect(panel).toContainText("E01 → E06 → E07 → E08 → E09");
  await expect(panel).toContainText("+3.20 公里");
  await expect(panel).toContainText("+4 分钟");
  await expect(panel.locator('[data-edge-id="E04"]')).toHaveAttribute("data-route-state", "blocked");
  await expect(panel.locator('[data-edge-id="E07"]')).toHaveAttribute("data-route-state", "recommended");
  await expect(panel.locator(".network-node")).toHaveCount(18);
  await expect(panel.locator(".road-edge")).toHaveCount(26);
  await page.screenshot({ path: path.join(screenshotDir, "road-blocked-reroute.png"), fullPage: true });
});
