import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const loader = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock("@amap/amap-jsapi-loader", () => ({ load: loader.load }));

import { AmapFleetMap } from "../src/components/amap-fleet-map";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type DrivingCallback = (status: string, result: { routes?: Array<{ steps?: Array<{ path?: unknown[] }> }> }) => void;

function createAmapApi(search: (...args: unknown[]) => void) {
  class FakeOverlay {
    constructor(public options: Record<string, unknown> = {}) {}
    on() {}
    open() {}
    close() {}
  }
  class FakeMap {
    on(eventName: string, listener: () => void) {
      if (eventName === "complete") queueMicrotask(listener);
    }
    add() {}
    remove() {}
    addControl() {}
    destroy() {}
    setLayers() {}
    setZoom() {}
    setPitch() {}
    setFitView() {}
    setCenter() {}
  }
  class FakeDriving {
    search(...args: unknown[]) {
      search(...args);
    }
  }
  const TileLayer = Object.assign(FakeOverlay, {
    Satellite: FakeOverlay,
    RoadNet: FakeOverlay,
    Traffic: FakeOverlay,
  });
  return {
    Map: FakeMap,
    Marker: FakeOverlay,
    Polyline: FakeOverlay,
    Circle: FakeOverlay,
    InfoWindow: FakeOverlay,
    Scale: FakeOverlay,
    ToolBar: FakeOverlay,
    Driving: FakeDriving,
    TileLayer,
  };
}

function renderMap(routeIds: string[]): { container: HTMLDivElement; root: Root } {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(<AmapFleetMap
      apiKey="web-key"
      securityCode="security-code"
      vehicles={[]}
      playing
      routeIds={routeIds}
      roadPlanningRouteIds={routeIds}
      nodeIds={[]}
      criticalRouteIds={[]}
      selectedVehicleId="V-001"
      blockedEdgeIds={[]}
      mapMode="SATELLITE"
      perspective={false}
      zoom={1}
      resetSequence={0}
      followVehicle={false}
      showLabels
      showRoutes
      showNodes
      showRiskAreas={false}
      showTraffic={false}
      geofenceMode={false}
      onFollowChange={vi.fn()}
      onVehicleSelect={vi.fn()}
      onRouteSelect={vi.fn()}
      onStateChange={vi.fn()}
    />);
  });
  return { container, root };
}

async function flushMapEffects(): Promise<void> {
  await act(async () => {
    for (let index = 0; index < 24; index += 1) await Promise.resolve();
  });
}

afterEach(() => {
  loader.load.mockReset();
  window.sessionStorage.clear();
  document.body.replaceChildren();
});

describe("AMap route loading performance", () => {
  it("starts two route matches in parallel instead of waiting for each vehicle route", async () => {
    const callbacks: DrivingCallback[] = [];
    loader.load.mockResolvedValue(createAmapApi((...args) => {
      callbacks.push(args[3] as DrivingCallback);
    }));

    const view = renderMap(["ROUTE-01", "ROUTE-02", "ROUTE-03", "ROUTE-04"]);
    await flushMapEffects();

    expect(callbacks).toHaveLength(2);
    callbacks[0]("complete", { routes: [{ steps: [{ path: [[103.05, 25.2], [103.08, 25.23]] }] }] });
    await flushMapEffects();
    expect(callbacks).toHaveLength(3);

    act(() => view.root.unmount());
  });

  it("reuses matched road geometry when the user returns to the fleet map", async () => {
    let drivingCalls = 0;
    loader.load.mockResolvedValue(createAmapApi((...args) => {
      drivingCalls += 1;
      const callback = args[3] as DrivingCallback;
      callback("complete", { routes: [{ steps: [{ path: [[103.05, 25.2], [103.08, 25.23]] }] }] });
    }));

    const firstView = renderMap(["ROUTE-01"]);
    await flushMapEffects();
    expect(firstView.container.querySelector('[data-road-planned-count="1"]')).not.toBeNull();
    act(() => firstView.root.unmount());

    const secondView = renderMap(["ROUTE-01"]);
    await flushMapEffects();
    expect(secondView.container.querySelector('[data-road-planned-count="1"]')).not.toBeNull();
    expect(drivingCalls).toBe(1);

    act(() => secondView.root.unmount());
  });
});
