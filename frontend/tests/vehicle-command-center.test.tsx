import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";

import { VehicleCommandCenter } from "../src/components/vehicle-command-center";
import { demoVehicleOperationSnapshot } from "../src/features/fleet-sandbox/vehicle-operation-demo";


(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("V8 vehicle command center", () => {
  it("does not expose a diagnosis or fixed recovery time before repair starts", async () => {
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    const scheduled = {
      ...demoVehicleOperationSnapshot,
      maintenance: {
        ...demoVehicleOperationSnapshot.maintenance,
        status: "SCHEDULED",
        diagnosis: "不应提前展示的诊断",
        progress_percent: 0,
        countdown_seconds: null,
        available_after: null,
      },
    };

    await act(async () => root.render(<VehicleCommandCenter snapshot={scheduled} connection="CONNECTED" />));

    const maintenanceCard = container.querySelector(".operation-maintenance-card");
    expect(maintenanceCard?.textContent).toContain("车辆到站后开始诊断");
    expect(maintenanceCard?.textContent).toContain("维修开始后生成");
    expect(maintenanceCard?.textContent).not.toContain("不应提前展示的诊断");
    expect(maintenanceCard?.textContent).not.toContain("20:42");
    expect(maintenanceCard?.textContent).not.toContain("演示时间已压缩");

    await act(async () => root.unmount());
    container.remove();
  });

  it("shows topology-backed response routes, four stages, maintenance countdown, and controls", async () => {
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    await act(async () => root.render(<VehicleCommandCenter snapshot={demoVehicleOperationSnapshot} connection="CONNECTED" />));

    expect(container.textContent).toContain("车辆故障 · 自动处置中");
    expect(container.querySelectorAll("[data-operation-stage]")).toHaveLength(4);
    expect(container.querySelectorAll("[data-operation-route]")).toHaveLength(4);
    expect(container.textContent).toContain("WX-20260910-018");
    expect(container.textContent).toContain("00:58");
    expect(container.querySelector('button[aria-label="放大地图"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="适配全景"]')).not.toBeNull();

    await act(async () => root.unmount());
    container.remove();
  });
});
