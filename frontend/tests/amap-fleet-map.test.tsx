import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const loader = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock("@amap/amap-jsapi-loader", () => ({ load: loader.load }));

import { AmapFleetMap } from "../src/components/amap-fleet-map";
import { pointAlongLngLatPath } from "../src/features/fleet-sandbox/fleet-amap-coordinates";
import type { FleetPositionSnapshot } from "../src/features/fleet-sandbox/fleet-simulation";
import { demoVehicleOperationSnapshot } from "../src/features/fleet-sandbox/vehicle-operation-demo";
import type { VehicleOperationSnapshot } from "../src/types/vehicle-operations";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderMap(
  onStateChange = vi.fn(),
  options: {
    vehicles?: FleetPositionSnapshot[];
    routeIds?: string[];
    roadPlanningRouteIds?: string[];
    followVehicle?: boolean;
    onFollowChange?: (following: boolean) => void;
    operationSnapshot?: VehicleOperationSnapshot | null;
    mapMode?: "STANDARD" | "SATELLITE";
  } = {},
) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(<AmapFleetMap
      apiKey="web-key"
      securityCode="security-code"
      vehicles={options.vehicles ?? []}
      playing
      routeIds={options.routeIds ?? []}
      roadPlanningRouteIds={options.roadPlanningRouteIds}
      nodeIds={[]}
      criticalRouteIds={[]}
      selectedVehicleId="V-001"
      blockedEdgeIds={[]}
      mapMode={options.mapMode ?? "SATELLITE"}
      perspective={false}
      zoom={1}
      resetSequence={0}
      followVehicle={options.followVehicle ?? false}
      showLabels
      showRoutes
      showNodes
      showRiskAreas
      showTraffic={false}
      geofenceMode={false}
      onFollowChange={options.onFollowChange ?? vi.fn()}
      operationSnapshot={options.operationSnapshot ?? null}
      onVehicleSelect={vi.fn()}
      onRouteSelect={vi.fn()}
      onStateChange={onStateChange}
    />);
  });
  return { container, root, onStateChange };
}

afterEach(() => {
  loader.load.mockReset();
  document.body.replaceChildren();
});

describe("AMap fleet map", () => {
  it("keeps an explicit loading state while the remote map SDK is pending", () => {
    loader.load.mockReturnValue(new Promise(() => undefined));
    const view = renderMap();
    expect(view.container.querySelector('[data-amap-state="LOADING"]')).not.toBeNull();
    expect(view.container.textContent).toContain("正在加载高德实时地图");
    expect(view.onStateChange).toHaveBeenCalledWith("LOADING");
    act(() => view.root.unmount());
  });

  it("reports a local-map fallback without exposing provider error details", async () => {
    loader.load.mockRejectedValue(new Error("authorization details must stay private"));
    const view = renderMap();
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(view.container.querySelector('[data-amap-state="FALLBACK"]')).not.toBeNull();
    expect(view.container.textContent).toContain("已切换本地卫星地图");
    expect(view.container.textContent).not.toContain("authorization details");
    expect(view.onStateChange).toHaveBeenLastCalledWith("FALLBACK");
    act(() => view.root.unmount());
  });

  it("plans only the requested business routes and positions vehicles on the same road geometry", async () => {
    const drivingCalls: unknown[][] = [];
    const markerOptions: Record<string, unknown>[] = [];
    const polylineOptions: Record<string, unknown>[] = [];
    const infoWindowOptions: Record<string, unknown>[] = [];
    const markerPositionUpdates: unknown[] = [];
    const mapCenterUpdates: unknown[] = [];
    const mapStyleUpdates: string[] = [];
    let animationFrame: FrameRequestCallback | undefined;
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      animationFrame = callback;
      return 1;
    }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    const mapListeners = new Map<string, () => void>();
    let mapOptions: Record<string, unknown> | undefined;
    const plannedPath = [[103.051, 25.22], [103.08, 25.23], [103.135, 25.261]] as const;

    class FakeOverlay {
      constructor(public options: Record<string, unknown> = {}) {}
      on() {}
      open() {}
    }
    class FakeMarker extends FakeOverlay {
      constructor(options: Record<string, unknown> = {}) {
        super(options);
        markerOptions.push(options);
      }
      setPosition(position: unknown) {
        markerPositionUpdates.push(position);
      }
    }
    class FakePolyline extends FakeOverlay {
      constructor(options: Record<string, unknown> = {}) {
        super(options);
        polylineOptions.push(options);
      }
    }
    class FakeInfoWindow extends FakeOverlay {
      constructor(options: Record<string, unknown> = {}) {
        super(options);
        infoWindowOptions.push(options);
      }
    }
    class FakeMap {
      constructor(_container: HTMLElement, options: Record<string, unknown>) {
        mapOptions = options;
      }
      on(eventName: string, listener: () => void) {
        mapListeners.set(eventName, listener);
        if (eventName === "complete") queueMicrotask(listener);
      }
      add() {}
      remove() {}
      addControl() {}
      destroy() {}
      setLayers() {}
      setMapStyle(style: string) {
        mapStyleUpdates.push(style);
      }
      setZoom() {}
      setPitch() {}
      setFitView() {}
      setCenter(position: unknown) {
        mapCenterUpdates.push(position);
      }
    }
    class FakeDriving {
      search(...args: unknown[]) {
        drivingCalls.push(args);
        const callback = args[3] as (status: string, result: unknown) => void;
        if (drivingCalls.length === 1) {
          callback("error", {});
          return;
        }
        callback("complete", { routes: [{ steps: [{ path: plannedPath }] }] });
      }
    }
    const TileLayer = Object.assign(FakeOverlay, {
      Satellite: FakeOverlay,
      RoadNet: FakeOverlay,
      Traffic: FakeOverlay,
    });
    loader.load.mockResolvedValue({
      Map: FakeMap,
      Marker: FakeMarker,
      Polyline: FakePolyline,
      Circle: FakeOverlay,
      InfoWindow: FakeInfoWindow,
      Scale: FakeOverlay,
      ToolBar: FakeOverlay,
      Driving: FakeDriving,
      TileLayer,
    });
    const vehicle: FleetPositionSnapshot = {
      id: "V-001",
      routeId: "ROUTE-01",
      status: "IN_TRANSIT",
      initialStep: 0,
      speedKph: 40,
      loadKg: 400,
      capacityKg: 1200,
      x: 0,
      y: 0,
      nodeId: "N19",
      locationLabel: "杨林大道",
      progress: 50,
      routeProgress: 0.5,
      routePhase: 0.5,
      routeDisplayName: "路线-01 · 调度中心—快递集散线",
    };
    const vehicles: FleetPositionSnapshot[] = [
      vehicle,
      { ...vehicle, id: "V-002", status: "DISPATCHING", speedKph: 46 },
      { ...vehicle, id: "V-003", status: "AVAILABLE", speedKph: 0 },
      { ...vehicle, id: "V-004", status: "MAINTENANCE", speedKph: 0 },
      { ...vehicle, id: "V-005", status: "BROKEN", speedKph: 0 },
    ];
    const onFollowChange = vi.fn();
    const view = renderMap(vi.fn(), {
      vehicles,
      routeIds: ["ROUTE-01"],
      roadPlanningRouteIds: ["ROUTE-01"],
      followVehicle: true,
      onFollowChange,
      operationSnapshot: demoVehicleOperationSnapshot,
      mapMode: "STANDARD",
    });

    await act(async () => {
      for (let index = 0; index < 24; index += 1) await Promise.resolve();
    });

    expect(drivingCalls).toHaveLength(5);
    expect(mapOptions).toMatchObject({
      mapStyle: "amap://styles/darkblue",
      dragEnable: true,
      scrollWheel: true,
      doubleClickZoom: true,
      touchZoom: true,
    });
    expect(view.container.querySelector('[data-amap-theme="night"]')).not.toBeNull();
    expect(mapStyleUpdates).toContain("amap://styles/darkblue");
    expect(mapListeners.has("dragend")).toBe(true);
    const vehicleMarker = markerOptions.find((options) =>
      (options.content as HTMLElement | undefined)?.classList.contains("amap-fleet-vehicle"));
    const expectedPosition = pointAlongLngLatPath(plannedPath, 0.5);
    expect(vehicleMarker?.position).toEqual(expectedPosition);
    expect((vehicleMarker?.content as HTMLElement).dataset.amapRouteId).toBe("ROUTE-01");
    expect(vehicleMarker?.bubble).toBe(true);
    expect((vehicleMarker?.content as HTMLElement).dataset.amapLng).toBe(String(expectedPosition[0]));
    expect((vehicleMarker?.content as HTMLElement).dataset.amapHeading).toMatch(/^-?\d+$/);
    const vehicleContents = markerOptions
      .map((options) => options.content as HTMLElement | undefined)
      .filter((content): content is HTMLElement => Boolean(content?.classList.contains("amap-fleet-vehicle")));
    const vehicleContent = (vehicleId: string) => vehicleContents.find((content) =>
      content.getAttribute("aria-label")?.startsWith(vehicleId));
    expect(vehicleContent("V-001")?.dataset.vehicleVisualState).toBe("moving");
    expect(vehicleContent("V-002")?.dataset.vehicleVisualState).toBe("dispatching");
    expect(vehicleContent("V-003")?.dataset.vehicleVisualState).toBe("standby");
    expect(vehicleContent("V-004")?.dataset.vehicleVisualState).toBe("standby");
    expect(vehicleContent("V-005")?.dataset.vehicleVisualState).toBe("fault");
    const movingVehicle = vehicleContent("V-001");
    const topViewVehicle = movingVehicle?.querySelector<HTMLImageElement>('[data-vehicle-sprite="top-view"]');
    expect(topViewVehicle?.getAttribute("src")).toBe("/assets/fleet/vehicle-top-view.png");
    expect(topViewVehicle?.getAttribute("alt")).toBe("");
    expect(movingVehicle?.querySelectorAll("[data-vehicle-radar-ring]")).toHaveLength(2);
    expect(movingVehicle?.querySelector("[data-vehicle-heading-indicator]")).not.toBeNull();
    expect(vehicleContent("V-002")?.querySelector("[data-vehicle-state-label]")?.textContent).toBe("调度中");
    expect(vehicleContent("V-005")?.querySelector("[data-vehicle-state-label]")?.textContent).toBe("故障");
    expect(vehicleContent("V-001")?.dataset.dispatchRole).toBe("incident");
    expect(vehicleContent("V-001")?.querySelector("[data-dispatch-role-label]")?.textContent).toBe("故障来源");
    expect(vehicleContent("V-005")?.dataset.dispatchRole).toBe("replacement");
    expect(vehicleContent("V-005")?.querySelector("[data-dispatch-role-label]")?.textContent).toBe("接管车辆");
    const selectedInfo = infoWindowOptions.at(-1)?.content as HTMLElement | undefined;
    expect(infoWindowOptions.at(-1)?.closeWhenClickMap).toBe(false);
    expect(infoWindowOptions.at(-1)?.anchor).toBe("middle-left");
    expect(infoWindowOptions.at(-1)?.offset).toEqual([46, 0]);
    expect(selectedInfo?.textContent).toContain("V-001");
    expect(selectedInfo?.textContent).toContain("40 km/h");
    expect(selectedInfo?.textContent).toContain("行驶中");
    expect(selectedInfo?.textContent).toContain("路线-01");
    const legend = view.container.querySelector('[aria-label="车辆状态图例"]');
    expect(Array.from(legend?.querySelectorAll("span") ?? []).map((item) => item.textContent)).toEqual([
      "行驶中",
      "调度中",
      "待命",
      "故障",
    ]);
    expect(legend?.querySelectorAll('[data-vehicle-sprite="top-view"]')).toHaveLength(4);
    expect(view.container.querySelector("[data-road-route-count=\"1\"]")).not.toBeNull();
    expect(view.container.querySelector("[data-road-planned-count=\"1\"]")).not.toBeNull();
    expect(view.container.querySelector("[data-operation-road-count=\"3\"]")).not.toBeNull();
    expect(polylineOptions.filter((options) => options.showDir === true).length).toBeGreaterThanOrEqual(3);
    expect(markerOptions.some((options) =>
      (options.content as HTMLElement | undefined)?.classList.contains("amap-fleet-rescue-unit"))).toBe(true);
    expect(animationFrame).toBeTypeOf("function");
    await act(async () => { animationFrame?.(performance.now() + 500); });
    expect(markerPositionUpdates.length).toBeGreaterThan(0);
    expect(markerPositionUpdates.at(-1)).not.toEqual(expectedPosition);
    expect(mapCenterUpdates.length).toBeGreaterThan(0);
    act(() => mapListeners.get("dragstart")?.());
    expect(onFollowChange).toHaveBeenCalledWith(false);
    act(() => view.root.unmount());
  });
});
