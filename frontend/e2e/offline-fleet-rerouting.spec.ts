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

function pathEvidence(
  nodeIds: string[],
  edgeIds: string[],
  distanceKm: string,
  minutes: number,
  riskCost: string,
  visitedNodeCount: number,
  scoringFormula: string | null = null,
) {
  return {
    objective: "FASTEST",
    node_ids: nodeIds,
    edge_ids: edgeIds,
    distance_km: distanceKm,
    estimated_minutes: minutes,
    risk_cost: riskCost,
    visited_node_count: visitedNodeCount,
    scoring_formula: scoringFormula,
  };
}

const roadNodeRows = [
  ["N01", "新平县中心仓", "0.00", "0.00", "STATION"],
  ["N02", "西环路口", "2.00", "0.00", "JUNCTION"],
  ["N03", "新平路西口", "2.00", "2.00", "JUNCTION"],
  ["N04", "新平路 K3.2", "5.00", "2.00", "INCIDENT_POINT"],
  ["N05", "东河桥", "8.00", "2.00", "BRIDGE"],
  ["N06", "城东配送站", "10.00", "2.00", "STATION"],
  ["N07", "102 国道西口", "2.00", "-2.00", "JUNCTION"],
  ["N08", "102 国道中段", "6.00", "-2.00", "JUNCTION"],
  ["N09", "102 国道东口", "9.00", "-1.00", "JUNCTION"],
  ["N10", "308 县道口", "0.00", "3.00", "JUNCTION"],
  ["N11", "北岭村驿站", "4.00", "6.00", "STATION"],
  ["N12", "河西乡服务站", "-3.00", "2.00", "STATION"],
  ["N13", "南山村服务点", "7.00", "-5.00", "STATION"],
  ["N14", "新平冷链中心", "1.00", "-1.00", "STATION"],
  ["N15", "县域车辆维修站", "4.00", "1.00", "STATION"],
  ["N16", "河西农资路口", "-1.00", "4.00", "JUNCTION"],
  ["N17", "城东电商服务点", "11.00", "4.00", "STATION"],
  ["N18", "双河村路口", "12.00", "0.00", "JUNCTION"],
] as const;

const roadEdgeRows = [
  ["E01", "中心仓连接线", "N01", "N02", "1.50", 3, "COUNTY", "LOW", "8.00"],
  ["E02", "西环至新平路", "N02", "N03", "1.50", 3, "COUNTY", "LOW", "8.00"],
  ["E03", "新平路西段", "N03", "N04", "2.00", 4, "COUNTY", "MEDIUM", "6.00"],
  ["E04", "新平路东河桥段", "N04", "N05", "2.50", 5, "COUNTY", "HIGH", "6.00"],
  ["E05", "东河桥连接线", "N05", "N06", "2.50", 5, "TOWN", "LOW", "5.00"],
  ["E06", "102 国道引道", "N02", "N07", "2.00", 4, "COUNTY", "LOW", "10.00"],
  ["E07", "102 国道西段", "N07", "N08", "4.00", 7, "NATIONAL", "LOW", "20.00"],
  ["E08", "102 国道东段", "N08", "N09", "3.20", 6, "NATIONAL", "LOW", "20.00"],
  ["E09", "国道至城东站", "N09", "N06", "2.50", 4, "COUNTY", "LOW", "8.00"],
  ["E10", "中心仓至 308 线", "N01", "N10", "3.10", 6, "COUNTY", "MEDIUM", "8.00"],
  ["E11", "308 县道北岭段", "N10", "N11", "5.50", 11, "COUNTY", "MEDIUM", "5.00"],
  ["E12", "308 县道农资段", "N10", "N16", "2.00", 4, "COUNTY", "LOW", "7.00"],
  ["E13", "河西农资支线", "N16", "N12", "4.00", 8, "TOWN", "LOW", "5.00"],
  ["E14", "河西回仓线", "N12", "N01", "3.60", 7, "TOWN", "LOW", "5.00"],
  ["E15", "102 国道南山支线", "N08", "N13", "4.50", 9, "VILLAGE", "MEDIUM", "3.50"],
  ["E16", "南山东接线", "N13", "N09", "5.20", 10, "VILLAGE", "MEDIUM", "3.50"],
  ["E17", "城东电商北线", "N06", "N17", "3.50", 7, "TOWN", "LOW", "5.00"],
  ["E18", "电商双河线", "N17", "N18", "4.00", 8, "VILLAGE", "LOW", "3.50"],
  ["E19", "双河城东线", "N18", "N06", "2.80", 6, "VILLAGE", "LOW", "3.50"],
  ["E20", "维修站接驳线", "N15", "N04", "2.80", 6, "TOWN", "LOW", "5.00"],
  ["E21", "维修站国道线", "N15", "N08", "3.00", 6, "COUNTY", "LOW", "8.00"],
  ["E22", "冷链中心回仓线", "N14", "N01", "1.10", 3, "TOWN", "LOW", "5.00"],
  ["E23", "冷链中心国道线", "N14", "N07", "2.50", 5, "COUNTY", "LOW", "8.00"],
  ["E24", "北岭电商山路", "N11", "N17", "8.00", 15, "VILLAGE", "HIGH", "2.00"],
  ["E25", "东河桥电商线", "N05", "N17", "3.10", 6, "TOWN", "LOW", "5.00"],
  ["E26", "国道双河线", "N09", "N18", "3.30", 6, "COUNTY", "LOW", "8.00"],
] as const;

function networkNodes() {
  return roadNodeRows.map(([nodeId, name, xKm, yKm, nodeType]) => ({
    node_id: nodeId,
    name,
    x_km: xKm,
    y_km: yKm,
    node_type: nodeType,
  }));
}

function networkEdges() {
  return roadEdgeRows.map(([edgeId, name, fromNodeId, toNodeId, distanceKm, baseMinutes, roadLevel, riskLevel, weightLimitTons]) => ({
    edge_id: edgeId,
    name,
    from_node_id: fromNodeId,
    to_node_id: toNodeId,
    distance_km: distanceKm,
    base_minutes: baseMinutes,
    road_level: roadLevel,
    risk_level: riskLevel,
    status: edgeId === "E04" ? "BLOCKED" : "OPEN",
    congestion_factor: "1.00",
    weight_limit_tons: weightLimitTons,
    bidirectional: true,
    version: edgeId === "E04" ? 8 : 7,
  }));
}


function unchangedFleetAllocation() {
  return {
    original_vehicle_id: "V-008", target_vehicle_id: "V-008", target_driver_id: "D-007", vehicle_reassigned: false,
    candidate_vehicles: [{ vehicle_id: "V-008", driver_id: "D-007", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY", remaining_capacity_kg: "1300.00", gross_weight_tons: "4.50", cargo_capability: "GENERAL", pickup_route: null, pickup_distance_km: "0.00", pickup_eta_minutes: 0, score: "100.0", score_components: null, scoring_formula: "FLEET_SCORE_V1", eligible: true, exclusion_reasons: [] }],
    pickup_route: null,
    scoring_formula: "FLEET_SCORE_V1",
  };
}

function unblockedRoutePlan() {
  const path = pathEvidence(["N04", "N05", "N06"], ["E04", "E05"], "5.00", 10, "0", 4, "ROUTE_SCORE_V1");
  return {
    original_path: path, recommended_path: path, candidate_routes: [], blocked_edge_ids: [],
    distance_delta_km: "0.00", eta_delta_minutes: 0, visited_node_count: 4, routing_status: "ROUTED",
    algorithm: "DIJKSTRA_V1", road_network_version: 7, network_nodes: networkNodes(),
    network_edges: networkEdges().map((edge) => edge.edge_id === "E04" ? { ...edge, status: "OPEN", version: 7 } : edge),
  };
}

function rejectedCandidate(
  vehicleId: string,
  driverId: string | null,
  vehicleStatus: string,
  driverStatus: string | null,
  remainingCapacityKg: string,
  grossWeightTons: string,
  cargoCapability: string,
  exclusionReasons: string[],
) {
  return {
    vehicle_id: vehicleId,
    driver_id: driverId,
    vehicle_status: vehicleStatus,
    driver_status: driverStatus,
    remaining_capacity_kg: remainingCapacityKg,
    gross_weight_tons: grossWeightTons,
    cargo_capability: cargoCapability,
    pickup_route: null,
    pickup_distance_km: null,
    pickup_eta_minutes: null,
    score: null,
    score_components: null,
    scoring_formula: "FLEET_SCORE_V1",
    eligible: false,
    exclusion_reasons: exclusionReasons,
  };
}

function fleetCandidates() {
  return [
    {
      vehicle_id: "V-005",
      driver_id: "D-003",
      vehicle_status: "AVAILABLE",
      driver_status: "ON_DUTY",
      remaining_capacity_kg: "900.00",
      gross_weight_tons: "2.40",
      cargo_capability: "COLD_CHAIN",
      pickup_route: pathEvidence(["N15", "N04"], ["E20"], "2.80", 6, "0", 2),
      pickup_distance_km: "2.80",
      pickup_eta_minutes: 6,
      score: "93.4",
      score_components: {
        eta_penalty: "9.0",
        distance_penalty: "5.60",
        load_penalty: "2.0",
        road_risk_penalty: "0",
        same_station_bonus: "0",
        cargo_exact_match_bonus: "10",
      },
      scoring_formula: "FLEET_SCORE_V1",
      eligible: true,
      exclusion_reasons: [],
    },
    rejectedCandidate("V-001", "D-001", "IN_TRANSIT", "BUSY", "800.00", "2.80", "COLD_CHAIN", ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE", "DRIVER_UNAVAILABLE"]),
    rejectedCandidate("V-002", "D-002", "AVAILABLE", "ON_DUTY", "1000.00", "2.20", "GENERAL", ["CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-003", null, "AVAILABLE", null, "400.00", "2.00", "GENERAL", ["DRIVER_UNAVAILABLE", "INSUFFICIENT_CAPACITY", "CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-004", "D-004", "IN_TRANSIT", "BUSY", "1800.00", "5.50", "FARM_SUPPLY", ["VEHICLE_UNAVAILABLE", "DRIVER_UNAVAILABLE", "CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-006", "D-005", "MAINTENANCE", "OFF_DUTY", "900.00", "1.80", "GENERAL", ["VEHICLE_UNAVAILABLE", "DRIVER_UNAVAILABLE", "CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-007", "D-006", "AVAILABLE", "ON_DUTY", "250.00", "0.80", "GENERAL", ["INSUFFICIENT_CAPACITY", "CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-008", "D-007", "AVAILABLE", "ON_DUTY", "1300.00", "4.50", "GENERAL", ["CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-009", "D-008", "IN_TRANSIT", "BUSY", "1100.00", "3.00", "COLD_CHAIN", ["VEHICLE_UNAVAILABLE", "DRIVER_UNAVAILABLE"]),
    rejectedCandidate("V-010", "D-009", "AVAILABLE", "ON_DUTY", "3000.00", "6.50", "FARM_SUPPLY", ["CARGO_CAPABILITY_MISMATCH"]),
    rejectedCandidate("V-011", null, "AVAILABLE", null, "500.00", "3.20", "COLD_CHAIN", ["DRIVER_UNAVAILABLE", "INSUFFICIENT_CAPACITY"]),
    rejectedCandidate("V-012", "D-010", "AVAILABLE", "ON_DUTY", "700.00", "2.00", "GENERAL", ["CARGO_CAPABILITY_MISMATCH"]),
  ];
}

function publicationResult(published: boolean, routeId: string) {
  return {
    status: published ? "PUBLISHED" : "PENDING",
    route_id: published ? routeId : null,
    route_instruction: published ? `请按 ${routeId} 行驶。` : null,
    published_at: published ? now : null,
    published_by: published ? "王主管" : null,
    recipient_employee_id: "CF-DEMO-001",
    recipient_display_name: "张师傅",
  };
}

function targetRouteId(taskId: string) {
  return taskId === taskByAnomaly.VEHICLE_BREAKDOWN ? "RTE-FLEET-V005" : "RTE-F2DD28EA7BC56B05";
}

function baseResult(taskId: string, orderId: number, published: boolean) {
  const routeId = targetRouteId(taskId);
  return {
    task_id: taskId,
    order_id: orderId,
    ready: true,
    status: "COMPLETED",
    anomaly_type: taskId === taskByAnomaly.VEHICLE_BREAKDOWN ? "VEHICLE_BREAKDOWN" : "ROAD_BLOCKED",
    dispatch: {
      dispatch_id: orderId + 100,
      dispatch_no: `DSP-${orderId}`,
      original_route_id: "RTE-NEWPING",
      target_route_id: routeId,
      status: "REROUTED",
      decision_reason: "离线县域沙盘完成确定性计算",
      fallback_used: false,
      fallback_reason: null,
      version: 1,
      executed: true,
    },
    audit: { result: "APPROVED", reason: "证据完整", dispatch_id: orderId + 100, created_at: now },
    publication: publicationResult(published, routeId),
  };
}

function breakdownResult(published: boolean) {
  return {
    ...baseResult(taskByAnomaly.VEHICLE_BREAKDOWN, 1, published),
    vehicle_allocation: {
      original_vehicle_id: "V-001",
      target_vehicle_id: "V-005",
      target_driver_id: "D-003",
      vehicle_reassigned: true,
      candidate_vehicles: fleetCandidates(),
      pickup_route: pathEvidence(["N15", "N04"], ["E20"], "2.80", 6, "0", 2),
      scoring_formula: "FLEET_SCORE_V1",
    },
    route_plan: unblockedRoutePlan(),
  };
}

function blockedResult(published: boolean) {
  return {
    ...baseResult(taskByAnomaly.ROAD_BLOCKED, 5, published),
    vehicle_allocation: unchangedFleetAllocation(),
    route_plan: {
      original_path: pathEvidence(["N01", "N02", "N03", "N04", "N05", "N06"], ["E01", "E02", "E03", "E04", "E05"], "10.00", 20, "16", 14),
      recommended_path: pathEvidence(["N01", "N02", "N07", "N08", "N09", "N06"], ["E01", "E06", "E07", "E08", "E09"], "13.20", 24, "0", 14, "ROUTE_SCORE_V1"),
      candidate_routes: [{
        route_id: "RTE-F2DD28EA7BC56B05",
        route_name: "FASTEST route",
        objective: "FASTEST",
        node_ids: ["N01", "N02", "N07", "N08", "N09", "N06"],
        edge_ids: ["E01", "E06", "E07", "E08", "E09"],
        distance_km: "13.20",
        estimated_minutes: 24,
        risk_level: "low",
        risk_cost: "0",
        visited_node_count: 14,
        available: true,
        reason: null,
        score: "100.00",
        score_components: { normalized_minutes: "0", normalized_distance: "0", normalized_risk: "0", time_penalty: "0", distance_penalty: "0", risk_penalty: "0" },
        scoring_formula: "ROUTE_SCORE_V1",
        algorithm_version: "DIJKSTRA_V1",
        road_network_version: 8,
      }],
      blocked_edge_ids: ["E04"],
      distance_delta_km: "3.20",
      eta_delta_minutes: 4,
      visited_node_count: 14,
      routing_status: "ROUTED",
      algorithm: "DIJKSTRA_V1",
      road_network_version: 8,
      network_nodes: networkNodes(),
      network_edges: networkEdges(),
    },
  };
}

function visibleResult(taskId: string, published: boolean, canReview: boolean) {
  const result = taskId === taskByAnomaly.VEHICLE_BREAKDOWN ? breakdownResult(published) : blockedResult(published);
  if (published || canReview) return result;
  return {
    ...result,
    dispatch: result.dispatch ? { ...result.dispatch, target_route_id: null, decision_reason: null } : null,
    vehicle_allocation: null,
    route_plan: null,
  };
}

async function installOfflineApi(page: Page) {
  const publishedTasks = new Set<string>();
  await page.route("http://localhost:8001/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const authorization = request.headers().authorization ?? "";
    const canReview = authorization === "Bearer offline-ui-supervisor-token";
    if (url.pathname === "/health") return json(route, { status: "ok" });
    if (url.pathname === "/api/v1/auth/demo-employees") return json(route, [
      { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" },
      { employee_id: "CF-DEMO-003", display_name: "王主管", role: "SUPERVISOR" },
    ]);
    if (url.pathname === "/api/v1/auth/demo-session") {
      const input = request.postDataJSON() as { employee_id: string };
      const supervisor = input.employee_id === "CF-DEMO-003";
      return json(route, {
        access_token: supervisor ? "offline-ui-supervisor-token" : "offline-ui-employee-token",
        token_type: "bearer",
        expires_in: 3600,
        principal: {
          subject_id: supervisor ? "supervisor-offline-003" : "employee-offline-001",
          display_name: supervisor ? "王主管" : "张师傅",
          roles: [supervisor ? "SUPERVISOR" : "EMPLOYEE"],
          permissions: supervisor
            ? ["dispatch:read", "dispatch:create", "orders:read", "anomalies:read", "agents:read", "memory:read", "dispatch:review", "memory:mutate", "runtime:read", "runtime:override", "audit:read", "monitor:read"]
            : ["dispatch:read", "anomalies:report"],
          auth_method: "development_jwt",
          issued_at: now,
          expires_at: "2099-09-07T09:00:00Z",
        },
      });
    }
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
    const publishMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)\/publish$/);
    if (publishMatch && request.method() === "POST") {
      if (!canReview) return json(route, { code: "AUTHORIZATION_DENIED", message: "当前身份没有发布权限" }, 403);
      const taskId = publishMatch[1];
      publishedTasks.add(taskId);
      const routeId = targetRouteId(taskId);
      return json(route, {
        task_id: taskId,
        dispatch_id: (taskId === taskByAnomaly.VEHICLE_BREAKDOWN ? 1 : 5) + 100,
        ...publicationResult(true, routeId),
        duplicate: false,
      });
    }
    const resultMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)\/result$/);
    if (resultMatch) {
      const taskId = resultMatch[1];
      return json(route, visibleResult(taskId, publishedTasks.has(taskId), canReview));
    }
    const statusMatch = url.pathname.match(/^\/api\/v1\/dispatch-tasks\/(.+)$/);
    if (statusMatch) return json(route, { task_id: statusMatch[1], order_id: statusMatch[1] === taskByAnomaly.VEHICLE_BREAKDOWN ? 1 : 5, status: "COMPLETED", started_at: now, completed_at: now, created_at: now, ready: true, requires_manual_review: false });
    if (url.pathname === "/api/v1/ws-tickets") return json(route, { code: "UI_REGRESSION_NO_SOCKET", message: "确定性 UI 回归不连接 WebSocket" }, 503);
    if (url.pathname.startsWith("/api/v1/runtime/")) return json(route, { code: "RUNTIME_UNAVAILABLE", message: "确定性 UI 回归不模拟运行态线程" }, 503);
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

async function publishAsSupervisor(page: Page, taskId: string) {
  await authenticatePage(page, "SUPERVISOR", `/dispatch/${taskId}`);
  await expect(page.locator(".fleet-allocation-panel, .route-plan-result-panel")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "发布调度单" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  const published = page.waitForResponse((response) => (
    response.url().endsWith(`/api/v1/dispatch-tasks/${taskId}/publish`)
    && response.request().method() === "POST"
  ));
  await page.getByRole("button", { name: "发布调度单" }).click();
  expect((await published).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "调度路线已发布" })).toBeVisible();
}

async function expectUnpublishedDecisionRedacted(page: Page) {
  await expect(page.locator(".route-decision")).toContainText("待主管发布");
  await expect(page.locator(".route-decision")).not.toContainText("离线县域沙盘完成确定性计算");
}

async function expectPublishedVehicleEvidence(page: Page) {
  const overview = page.locator(".dispatch-evidence-overview");
  const presentationNav = page.getByRole("navigation", { name: "答辩讲解导航" });
  await expect(page.getByRole("heading", { name: "调度路线已发布" })).toBeVisible();
  await expect(overview.getByRole("heading", { name: "异常处置结果总览" })).toBeVisible();
  await expect(presentationNav).toContainText("处置总览");
  await expect(presentationNav).toContainText("车辆计算");
  await expect(presentationNav).toContainText("Agent 流水线");
  await expect(overview.getByLabel("计算证据来源")).toContainText("虚拟县域沙盘");
  await expect(overview.getByLabel("计算证据来源")).toContainText("未接入高德地图");
  await expect(overview.getByLabel("计算证据来源")).toContainText("API 持久化结果");
  await expect(overview).toContainText("V-001 车辆故障");
  await expect(overview).toContainText("比较 12 辆候选车辆");
  await expect(overview).toContainText("V-005 接替");
  await expect(overview).toContainText("评分 93.4");
  await expect(overview.getByRole("region", { name: "车辆调度计算对比" })).toContainText("候选 12 辆");
  await expect(overview.getByRole("region", { name: "车辆调度计算对比" })).toContainText("V-005 · D-003 · 93.4 分");
  await expect(overview).not.toContainText("道路堵塞重规划");
  const evidenceLink = overview.getByRole("link", { name: "查看车辆计算依据" });
  expect(await evidenceLink.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  await evidenceLink.click();
  await expect(page).toHaveURL(/#fleet-allocation-title$/);
  expect((await page.getByRole("heading", { name: "替代车辆调度计算" }).boundingBox())?.y ?? 0).toBeGreaterThanOrEqual(64);
  await expect(page.getByRole("heading", { name: "替代车辆调度计算" })).toBeVisible();
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-001");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("V-005");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("D-003");
  await expect(page.getByLabel("故障车辆到接替车辆")).toContainText("接驳 2.80 公里 · 6 分钟");
  await expect(page.locator(".fleet-score-summary")).toContainText("93.4");
  await expect(page.locator(".fleet-candidate-table tbody tr")).toHaveCount(12);
  await expect(page.getByLabel("V-001 候选车辆")).toContainText("原故障车辆不参与候选");
  await expect(page.getByLabel("V-005 候选车辆").locator('[data-field="remaining-capacity"]')).toContainText("900.00 千克");
  await expect(page.getByLabel("V-006 候选车辆")).toContainText("维护中");
  await expect(page.getByLabel("V-006 候选车辆")).toContainText("车辆当前不可用");
  await expect(page.getByLabel("V-006 候选车辆")).toContainText("司机当前不可用");
  await presentationNav.getByRole("link", { name: /Agent 流水线/ }).click();
  await expect(page).toHaveURL(/#agent-pipeline-title$/);
  await expect(page.getByRole("heading", { name: "智能体流水线" })).toBeVisible();
}

async function expectPublishedRouteEvidence(page: Page) {
  const overview = page.locator(".dispatch-evidence-overview");
  const panel = page.locator(".route-plan-result-panel");
  const presentationNav = page.getByRole("navigation", { name: "答辩讲解导航" });
  await expect(page.getByRole("heading", { name: "调度路线已发布" })).toBeVisible();
  await expect(presentationNav).toContainText("路线计算");
  await expect(overview.getByLabel("计算证据来源")).toContainText("虚拟县域沙盘");
  await expect(overview.getByLabel("计算证据来源")).toContainText("未接入高德地图");
  await expect(overview.getByLabel("计算证据来源")).toContainText("API 持久化结果");
  await expect(overview).toContainText("E04 道路堵塞");
  await expect(overview).toContainText("Dijkstra 访问 14 个节点");
  await expect(overview).toContainText("新路线 13.20 公里");
  await expect(overview).toContainText("已避开 E04");
  const comparison = overview.getByRole("region", { name: "路线重规划计算对比" });
  await expect(comparison).toContainText("10.00 公里 · 20 分钟");
  await expect(comparison).toContainText("移除 E04");
  await expect(comparison).toContainText("访问 14 个节点");
  await expect(comparison).toContainText("13.20 公里 · 24 分钟");
  await expect(comparison).toContainText("+3.20 公里 · +4 分钟");
  await expect(overview).not.toContainText("车辆故障处置");
  const evidenceLink = overview.getByRole("link", { name: "查看路线计算依据" });
  expect(await evidenceLink.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
  await evidenceLink.click();
  await expect(page).toHaveURL(/#route-plan-result-title$/);
  expect((await page.getByRole("heading", { name: "新路线规划计算" }).boundingBox())?.y ?? 0).toBeGreaterThanOrEqual(64);
  await expect(panel.getByRole("heading", { name: "新路线规划计算" })).toBeVisible();
  await expect(panel).toContainText("Dijkstra（DIJKSTRA_V1）");
  await expect(panel).toContainText("网络版本 8");
  await expect(panel).toContainText("N01 → N02 → N03 → N04 → N05 → N06");
  await expect(panel).toContainText("N01 → N02 → N07 → N08 → N09 → N06");
  await expect(panel).toContainText("E01 → E02 → E03 → E04 → E05");
  await expect(panel).toContainText("E01 → E06 → E07 → E08 → E09");
  await expect(panel).toContainText("+3.20 公里");
  await expect(panel).toContainText("+4 分钟");
  await expect(panel.locator('[data-edge-id="E04"]')).toHaveAttribute("data-route-state", "blocked");
  await expect(panel.locator('[data-edge-id="E07"]')).toHaveAttribute("data-route-state", "recommended");
  await expect(panel.locator(".network-node")).toHaveCount(18);
  await expect(panel.locator(".road-edge")).toHaveCount(26);
  await presentationNav.getByRole("link", { name: /Agent 流水线/ }).click();
  await expect(page).toHaveURL(/#agent-pipeline-title$/);
  await expect(page.getByRole("heading", { name: "智能体流水线" })).toBeVisible();
}


function observeBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    const location = message.location().url;
    const expectedOfflineDegradation = message.text().includes("503") && (
      location.endsWith("/api/v1/ws-tickets") || location.includes("/api/v1/runtime/")
    );
    if (message.type() === "error" && !expectedOfflineDegradation) errors.push(`${message.text()} @ ${location}`);
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function expectWideDesktopDispatchColumnsNotToOverlap(page: Page) {
  const decisionColumn = page.locator(".decision-column");
  const pipelineColumn = page.locator(".pipeline-column");
  const candidateTableWrap = page.locator(".fleet-candidate-table-wrap");
  const [decisionBox, pipelineBox, tableWrapBox] = await Promise.all([
    decisionColumn.boundingBox(),
    pipelineColumn.boundingBox(),
    candidateTableWrap.boundingBox(),
  ]);

  expect(decisionBox).not.toBeNull();
  expect(pipelineBox).not.toBeNull();
  expect(tableWrapBox).not.toBeNull();
  expect((decisionBox?.x ?? 0) + (decisionBox?.width ?? 0)).toBeLessThanOrEqual((pipelineBox?.x ?? 0) + 1);
  expect((tableWrapBox?.x ?? 0) + (tableWrapBox?.width ?? 0)).toBeLessThanOrEqual(
    (decisionBox?.x ?? 0) + (decisionBox?.width ?? 0) + 1,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
}

test.beforeEach(async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  await installOfflineApi(page);
  await authenticatePage(page, "EMPLOYEE", "/my-tasks");
});

test("网络拦截 UI 回归：车辆故障证据仅在主管发布后供员工查看，刷新重登仍一致", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const taskId = taskByAnomaly.VEHICLE_BREAKDOWN;
  await submitVisibleIssue(page, "SOURCE-DEMO-001", "VEHICLE_BREAKDOWN");
  await expect(page.getByRole("heading", { name: "调度路线待发布" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "替代车辆调度计算" })).toHaveCount(0);
  await expect(page.locator(".dispatch-evidence-overview")).toHaveCount(0);
  await expectUnpublishedDecisionRedacted(page);

  await publishAsSupervisor(page, taskId);
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskId}`);
  await expectPublishedVehicleEvidence(page);
  await expectWideDesktopDispatchColumnsNotToOverlap(page);

  await page.reload();
  await expect(page.getByRole("heading", { name: "需要登录" })).toBeVisible();
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskId}`);
  await expectPublishedVehicleEvidence(page);
  await expect(page).toHaveTitle("CountyFlow AI");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
  await page.screenshot({ path: path.join(screenshotDir, "vehicle-breakdown-candidates.png"), fullPage: true });
});

test("网络拦截 UI 回归：道路堵塞证据仅在主管发布后供员工查看，刷新重登仍一致", async ({ page }) => {
  const browserErrors = observeBrowserErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const taskId = taskByAnomaly.ROAD_BLOCKED;
  await submitVisibleIssue(page, "SOURCE-DEMO-005", "ROAD_BLOCKED");
  await expect(page.getByRole("heading", { name: "调度路线待发布" })).toBeVisible();
  await expect(page.locator(".route-plan-result-panel")).toHaveCount(0);
  await expect(page.locator(".dispatch-evidence-overview")).toHaveCount(0);
  await expectUnpublishedDecisionRedacted(page);

  await publishAsSupervisor(page, taskId);
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskId}`);
  await expectPublishedRouteEvidence(page);

  await page.reload();
  await expect(page.getByRole("heading", { name: "需要登录" })).toBeVisible();
  await authenticatePage(page, "EMPLOYEE", `/dispatch/${taskId}`);
  await expectPublishedRouteEvidence(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await expect(page).toHaveTitle("CountyFlow AI");
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  expect(browserErrors).toEqual([]);
  await page.screenshot({ path: path.join(screenshotDir, "road-blocked-reroute.png"), fullPage: true });
});
