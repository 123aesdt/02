import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://localhost:8001",
    authenticationMode: "development_jwt",
    runtimeThreadStateEnabled: true,
    amap: { enabled: true, key: "test-key", securityCode: "test-code" },
  },
}));

vi.mock("../src/components/amap-fleet-map", () => ({
  AmapFleetMap: () => {
    throw new Error("provider secret and Pixel(NaN, NaN)");
  },
}));

import { router } from "../src/app/router";
import { FleetSandboxMap } from "../src/components/fleet-sandbox-map";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function ThrowingRoute(): React.ReactNode {
  throw new Error("route internals must stay private");
}

function mount(element: React.ReactNode): { container: HTMLDivElement; root: Root; error: unknown } {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  let error: unknown;
  try {
    act(() => root.render(element));
  } catch (caught) {
    error = caught;
  }
  return { container, root, error };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

describe("application error recovery", () => {
  it("replaces an unexpected route crash with localized recovery actions", () => {
    const errorElement = router.routes[0]?.errorElement;
    expect(errorElement).toBeDefined();
    if (!errorElement) return;

    const memoryRouter = createMemoryRouter([
      { path: "/", element: <ThrowingRoute />, errorElement },
      { path: "/workspace", element: <h1>工作台</h1> },
    ]);
    const view = mount(<RouterProvider router={memoryRouter} />);

    expect(view.error).toBeUndefined();
    expect(view.container.textContent).toContain("页面暂时无法显示");
    expect(view.container.textContent).toContain("重新加载页面");
    expect(view.container.textContent).toContain("返回工作台");
    expect(view.container.textContent).not.toContain("route internals");
    act(() => view.root.unmount());
  });

  it("contains an AMap provider crash inside the map surface", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = mount(<FleetSandboxMap
      anomalyType="VEHICLE_BREAKDOWN"
      allocation={null}
      routePlan={null}
      connection="CONNECTED"
      reportedVehicleId="V-002"
      taskStatus="SUCCEEDED"
      events={[]}
    />);

    expect(view.error).toBeUndefined();
    expect(view.container.textContent).toContain("地图服务已安全降级");
    expect(view.container.textContent).toContain("重新连接高德地图");
    expect(view.container.querySelector(".fleet-sandbox-canvas")).not.toBeNull();
    expect(view.container.textContent).not.toContain("provider secret");
    act(() => view.root.unmount());
  });
});
