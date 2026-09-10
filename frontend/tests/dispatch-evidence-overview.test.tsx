import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DispatchEvidenceOverview } from "../src/components/dispatch-evidence-overview";
import type { RoutePlanResponse, VehicleAllocationResponse } from "../src/services/api/dispatch-adapter";

const unavailableAllocation: VehicleAllocationResponse = {
  original_vehicle_id: "V-001",
  target_vehicle_id: null,
  target_driver_id: null,
  vehicle_reassigned: false,
  candidate_vehicles: [{
    vehicle_id: "V-001", driver_id: "D-001", vehicle_status: "BROKEN", driver_status: "ON_DUTY",
    remaining_capacity_kg: "800.00", gross_weight_tons: "2.80", cargo_capability: "COLD_CHAIN",
    pickup_route: null, pickup_distance_km: null, pickup_eta_minutes: null, score: null,
    score_components: null, scoring_formula: "FLEET_SCORE_V1", eligible: false,
    exclusion_reasons: ["ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"],
  }],
  pickup_route: null,
  scoring_formula: "FLEET_SCORE_V1",
};

const unavailableRoutePlan: RoutePlanResponse = {
  original_path: null,
  recommended_path: null,
  candidate_routes: [],
  blocked_edge_ids: ["E04"],
  distance_delta_km: null,
  eta_delta_minutes: null,
  visited_node_count: 14,
  routing_status: "NO_REACHABLE_ROUTE",
  algorithm: "DIJKSTRA_V1",
  road_network_version: 8,
  network_nodes: [],
  network_edges: [],
};

const successfulAllocation: VehicleAllocationResponse = {
  ...unavailableAllocation,
  target_vehicle_id: "V-005",
  target_driver_id: "D-003",
  vehicle_reassigned: true,
  candidate_vehicles: [
    ...unavailableAllocation.candidate_vehicles,
    {
      vehicle_id: "V-005", driver_id: "D-003", vehicle_status: "AVAILABLE", driver_status: "ON_DUTY",
      remaining_capacity_kg: "900.00", gross_weight_tons: "2.40", cargo_capability: "COLD_CHAIN",
      pickup_route: null, pickup_distance_km: "2.80", pickup_eta_minutes: 6, score: "93.4",
      score_components: null, scoring_formula: "FLEET_SCORE_V1", eligible: true, exclusion_reasons: [],
    },
  ],
};

const successfulRoutePlan: RoutePlanResponse = {
  ...unavailableRoutePlan,
  original_path: { objective: "FASTEST", node_ids: ["N01", "N02", "N06"], edge_ids: ["E01", "E04"], distance_km: "10.00", estimated_minutes: 20, risk_cost: "1.00", visited_node_count: 8, scoring_formula: null },
  recommended_path: { objective: "FASTEST", node_ids: ["N01", "N07", "N06"], edge_ids: ["E06", "E09"], distance_km: "13.20", estimated_minutes: 24, risk_cost: "0.30", visited_node_count: 14, scoring_formula: "ROUTE_SCORE_V1" },
  distance_delta_km: "3.20",
  eta_delta_minutes: 4,
  routing_status: "ROUTED",
};
describe("DispatchEvidenceOverview", () => {
  it("does not claim a blocked road was avoided when no replacement route exists", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview routePlan={unavailableRoutePlan}/>);

    expect(markup).toContain("未找到可用新路线");
    expect(markup).toContain("需要人工复核异常道路");
    expect(markup).not.toContain("已避开 E04");
  });

  it("renders nothing until persisted calculation evidence is available", () => {
    expect(renderToStaticMarkup(<DispatchEvidenceOverview/>)).toBe("");
  });

  it("uses the persisted anomaly type to isolate a vehicle failure from paired route evidence", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview anomalyType="VEHICLE_BREAKDOWN" vehicleAllocation={unavailableAllocation} routePlan={unavailableRoutePlan}/>);

    expect(markup).toContain("车辆故障处置");
    expect(markup).toContain("未找到可用接替车辆");
    expect(markup).toContain("需要人工复核车辆调度");
    expect(markup).not.toContain("待选车辆 接替");
    expect(markup).not.toContain("道路堵塞重规划");
  });

  it("uses the persisted anomaly type to isolate a road blockage from paired fleet evidence", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview anomalyType="ROAD_BLOCKED" vehicleAllocation={unavailableAllocation} routePlan={unavailableRoutePlan}/>);

    expect(markup).toContain("道路堵塞重规划");
    expect(markup).not.toContain("车辆故障处置");
  });
  it("does not describe a general road hazard as a confirmed road blockage", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview anomalyType="ROAD_HAZARD" routePlan={unavailableRoutePlan}/>);

    expect(markup).toBe("");
  });
  it("shows vehicle comparison, provenance, and presentation navigation from persisted evidence", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview anomalyType="VEHICLE_BREAKDOWN" vehicleAllocation={successfulAllocation}/>);

    expect(markup).toContain("答辩讲解导航");
    expect(markup).toContain('href="#fleet-allocation-title"');
    expect(markup).toContain('href="#agent-pipeline-title"');
    expect(markup).toContain("虚拟县域沙盘");
    expect(markup).toContain("未接入高德地图");
    expect(markup).toContain("API 持久化结果");
    expect(markup).toContain("候选 2 辆");
    expect(markup).toContain("可调度 1 辆");
    expect(markup).toContain("排除 1 辆");
    expect(markup).toContain("V-005 · D-003 · 93.4 分");
  });

  it("compares the original and recalculated route with literal Dijkstra evidence", () => {
    const markup = renderToStaticMarkup(<DispatchEvidenceOverview anomalyType="ROAD_BLOCKED" routePlan={successfulRoutePlan}/>);

    expect(markup).toContain("原路线");
    expect(markup).toContain("10.00 公里 · 20 分钟");
    expect(markup).toContain("移除 E04");
    expect(markup).toContain("访问 14 个节点");
    expect(markup).toContain("新路线");
    expect(markup).toContain("13.20 公里 · 24 分钟");
    expect(markup).toContain("+3.20 公里 · +4 分钟");
  });
});
