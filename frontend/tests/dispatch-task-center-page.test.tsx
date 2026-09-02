import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../src/auth/auth-state";
import { ApiError } from "../src/services/api/client";

const workspaceApi = vi.hoisted(() => ({ getAnomalies: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://api.test",
    authenticationMode: "development_jwt",
  },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceApi }));

import { DispatchTaskCenterPage } from "../src/pages/dispatch-task-center-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const auth: AuthContextValue = {
  status: "authenticated",
  principal: null,
  permissions: ["dispatch:create"],
  error: null,
  demoEmployees: [],
  demoEmployeesLoading: false,
  logout: vi.fn(async () => undefined),
  switchDemoEmployee: vi.fn(async () => undefined),
};

const anomalyPage = {
  items: [
    {
      row_id: 42,
      anomaly_no: "ANOM-driver-42",
      order_no: "ORD-OWNED",
      driver_id: "driver-zhang",
      vehicle_id: "vehicle-001",
      route_id: "route-xinping",
      latest_task_id: "TASK-NEW",
      anomaly_type: "VEHICLE_BREAKDOWN",
      risk: "HIGH",
      description: "车辆出现异响，无法继续安全行驶。",
      status: "REPORTED",
      reported_at: "2026-09-01T08:30:00Z",
    },
    {
      row_id: 43,
      anomaly_no: "ANOM-waiting-43",
      order_no: "ORD-43",
      driver_id: "driver-chen",
      vehicle_id: "vehicle-006",
      route_id: "route-river",
      latest_task_id: null,
      anomaly_type: "ROAD_BLOCKED",
      risk: "MEDIUM",
      description: "道路暂时封闭。",
      status: "REPORTED",
      reported_at: "2026-09-01T08:31:00Z",
    },
  ],
  total: 2,
  next_cursor: null,
  provenance: "LIVE" as const,
};

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

async function renderPage() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<AuthContext.Provider value={auth}><MemoryRouter><DispatchTaskCenterPage /></MemoryRouter></AuthContext.Provider>); });
  await flush();
  return { container, root };
}

beforeEach(() => workspaceApi.getAnomalies.mockResolvedValue(anomalyPage));

afterEach(() => {
  workspaceApi.getAnomalies.mockReset();
  document.body.replaceChildren();
});

describe("dispatch task center", () => {
  it("lists anomaly-created tasks without the fixed submission scenario", async () => {
    const { container } = await renderPage();

    expect(container.querySelector("h1")?.textContent).toBe("异常调度任务");
    expect(container.textContent).toContain("ANOM-driver-42");
    expect(container.textContent).toContain("TASK-NEW");
    expect(container.querySelector('a[href="/dispatch/TASK-NEW"]')).not.toBeNull();
    expect(container.textContent).toContain("等待自动任务");
    expect(container.textContent).not.toContain("发起 AI 调度");
    expect(container.textContent).not.toContain("李师傅");
    expect(container.textContent).not.toContain("雨天道路湿滑");
  });

  it("shows an honest retry state instead of a mock task", async () => {
    workspaceApi.getAnomalies.mockRejectedValue(new ApiError(503, "UNAVAILABLE", "down"));

    const { container } = await renderPage();

    expect(container.textContent).toContain("异常调度任务暂不可用");
    expect(container.textContent).toContain("重试");
    expect(container.textContent).not.toContain("TASK-NEW");
  });
});
