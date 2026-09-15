import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    amap: { enabled: true, key: "test-key", securityCode: "test-code" },
  },
}));

vi.mock("../src/components/amap-fleet-map", () => ({
  AmapFleetMap: () => <div className="fleet-amap-stage is-loading" data-amap-state="LOADING">正在加载高德实时地图</div>,
}));

import { FleetSandboxMap } from "../src/components/fleet-sandbox-map";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.replaceChildren();
});

describe("fleet map loading surface", () => {
  it("does not flash the legacy map while AMap is loading", () => {
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    act(() => {
      root.render(<FleetSandboxMap
        anomalyType={null}
        allocation={null}
        routePlan={null}
        connection="CONNECTED"
      />);
    });

    expect(container.querySelector('[data-amap-state="LOADING"]')).not.toBeNull();
    expect(container.querySelector(".fleet-sandbox-canvas")).toBeNull();

    act(() => root.unmount());
  });
});
