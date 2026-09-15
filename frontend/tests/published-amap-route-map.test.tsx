import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const loader = vi.hoisted(() => ({ load: vi.fn() }));
const amapRuntime = vi.hoisted(() => ({ enabled: true }));
vi.mock("@amap/amap-jsapi-loader", () => ({ load: loader.load }));
vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    amap: { get enabled() { return amapRuntime.enabled; }, key: "web-key", securityCode: "security-code" },
  },
}));

import { PublishedAmapRouteMap } from "../src/components/published-amap-route-map";
import type { PublicationResultResponse, RoutePlanResponse } from "../src/services/api/dispatch-adapter";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const publication: PublicationResultResponse = {
  status: "PUBLISHED",
  route_id: "ROUTE-REAL-01",
  route_instruction: "避开新平路施工段，沿高德推荐道路驶往城东站。",
  published_at: "2026-09-15T09:30:00+08:00",
  published_by: "调度主管",
  recipient_employee_id: "CF-DEMO-001",
  recipient_display_name: "李师傅",
};

function routePlan(status: "VERIFIED" | "CLIENT_MATCH_REQUIRED"): RoutePlanResponse {
  return {
    original_path: null,
    recommended_path: {
      objective: "SAFEST",
      node_ids: ["N04", "N06", "N08"],
      edge_ids: ["E07", "E09"],
      distance_km: "5.80",
      estimated_minutes: 12,
      risk_cost: "0.20",
      visited_node_count: 6,
      scoring_formula: "ROUTE_SCORE_V1",
    },
    candidate_routes: [],
    blocked_edge_ids: ["E04"],
    distance_delta_km: "0.80",
    eta_delta_minutes: 2,
    visited_node_count: 6,
    routing_status: "ROUTED",
    algorithm: "DIJKSTRA_V1",
    road_network_version: 8,
    network_nodes: [],
    network_edges: [],
    real_road_route: {
      provider: "AMAP",
      source: status === "VERIFIED" ? "AMAP_WEB_SERVICE" : "CLIENT_WAYPOINT_FALLBACK",
      status,
      coordinate_system: "GCJ02",
      mapping_version: "DEMO_AMAP_V1",
      distance_meters: status === "VERIFIED" ? 5820 : null,
      duration_seconds: status === "VERIFIED" ? 710 : null,
      waypoints: [
        { node_id: "N04", longitude: "103.084211", latitude: "25.242106" },
        { node_id: "N06", longitude: "103.105892", latitude: "25.251844" },
        { node_id: "N08", longitude: "103.135041", latitude: "25.261342" },
      ],
      polyline: status === "VERIFIED" ? [
        { node_id: null, longitude: "103.084211", latitude: "25.242106" },
        { node_id: null, longitude: "103.096000", latitude: "25.247000" },
        { node_id: null, longitude: "103.135041", latitude: "25.261342" },
      ] : [
        { node_id: "N04", longitude: "103.084211", latitude: "25.242106" },
        { node_id: "N06", longitude: "103.105892", latitude: "25.251844" },
        { node_id: "N08", longitude: "103.135041", latitude: "25.261342" },
      ],
      fallback_reason: status === "VERIFIED" ? null : "服务端道路规划暂不可用，已交由司机端高德匹配。",
    },
  };
}

async function renderMap(plan: RoutePlanResponse): Promise<{ container: HTMLDivElement; root: Root }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<PublishedAmapRouteMap routePlan={plan} publication={publication}/>);
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
  return { container, root };
}

afterEach(() => {
  loader.load.mockReset();
  amapRuntime.enabled = true;
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("published AMap route map", () => {
  it("draws the server-verified polyline without asking AMap to plan it again", async () => {
    const polylines: Record<string, unknown>[] = [];
    const drivingSearch = vi.fn();
    class FakeMap { add() {} setFitView() {} destroy() {} }
    class FakeOverlay { constructor(public options: Record<string, unknown> = {}) {} }
    class FakePolyline extends FakeOverlay { constructor(options: Record<string, unknown>) { super(options); polylines.push(options); } }
    class FakeDriving { search = drivingSearch; }
    loader.load.mockResolvedValue({ Map: FakeMap, Marker: FakeOverlay, Polyline: FakePolyline, Driving: FakeDriving });

    const view = await renderMap(routePlan("VERIFIED"));

    expect(drivingSearch).not.toHaveBeenCalled();
    expect(polylines[0]?.path).toEqual([[103.084211, 25.242106], [103.096, 25.247], [103.135041, 25.261342]]);
    expect(view.container.querySelector('[data-published-route-state="READY"]')).not.toBeNull();
    expect(view.container.textContent).toContain("高德真实道路");
    expect(view.container.textContent).toContain("5.82 公里");
    expect(view.container.textContent).toContain("12 分钟");
    expect(view.container.textContent).toContain("避开新平路施工段");
    await act(async () => view.root.unmount());
  });

  it("matches waypoint-only evidence to AMap driving roads in the browser", async () => {
    const drivingSearch = vi.fn((_origin, _destination, _options, callback) => {
      callback("complete", { routes: [{ steps: [{ path: [[103.084211, 25.242106], [103.11, 25.255], [103.135041, 25.261342]] }] }] });
    });
    const polylines: Record<string, unknown>[] = [];
    class FakeMap { add() {} setFitView() {} destroy() {} }
    class FakeOverlay { constructor(public options: Record<string, unknown> = {}) {} }
    class FakePolyline extends FakeOverlay { constructor(options: Record<string, unknown>) { super(options); polylines.push(options); } }
    class FakeDriving { search = drivingSearch; }
    loader.load.mockResolvedValue({ Map: FakeMap, Marker: FakeOverlay, Polyline: FakePolyline, Driving: FakeDriving });

    const view = await renderMap(routePlan("CLIENT_MATCH_REQUIRED"));

    expect(drivingSearch).toHaveBeenCalledWith(
      [103.084211, 25.242106],
      [103.135041, 25.261342],
      { waypoints: [[103.105892, 25.251844]] },
      expect.any(Function),
    );
    expect(polylines[0]?.path).toEqual([[103.084211, 25.242106], [103.11, 25.255], [103.135041, 25.261342]]);
    expect(view.container.textContent).toContain("高德道路已匹配");
    await act(async () => view.root.unmount());
  });

  it("falls back to a safe local route card when the AMap SDK cannot load", async () => {
    loader.load.mockRejectedValue(new Error("secret authorization details"));
    const view = await renderMap(routePlan("CLIENT_MATCH_REQUIRED"));

    expect(view.container.querySelector("[data-published-route-fallback]")).not.toBeNull();
    expect(view.container.textContent).toContain("本地路线可继续使用");
    expect(view.container.textContent).not.toContain("secret authorization details");
    await act(async () => view.root.unmount());
  });

  it("keeps the published instructions visible when AMap is not configured", async () => {
    amapRuntime.enabled = false;
    const view = await renderMap(routePlan("CLIENT_MATCH_REQUIRED"));

    expect(loader.load).not.toHaveBeenCalled();
    expect(view.container.querySelector("[data-published-route-fallback]")).not.toBeNull();
    expect(view.container.textContent).toContain("避开新平路施工段");
    await act(async () => view.root.unmount());
  });
});
