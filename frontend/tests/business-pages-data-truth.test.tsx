import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";

const workspaceReadApi = vi.hoisted(() => ({
  getOrders: vi.fn(),
  getAnomalies: vi.fn(),
}));
const mockWorkspaceDataHooks = vi.hoisted(() => ({
  useAnomalies: vi.fn(() => []),
  useOrders: vi.fn(() => []),
}));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));
vi.mock("../src/hooks/use-workspace-data", () => mockWorkspaceDataHooks);
vi.mock("../src/hooks/use-workspace-reads", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/hooks/use-workspace-reads")>();
  return {
    ...actual,
    useAnomaliesRead: vi.fn(actual.useAnomaliesRead),
    useOrdersRead: vi.fn(actual.useOrdersRead),
  };
});

import { runtimeConfig } from "../src/config/runtime";
import { useAnomaliesRead, useOrdersRead } from "../src/hooks/use-workspace-reads";
import { AnomaliesPage } from "../src/pages/anomalies-page";
import { OrdersPage } from "../src/pages/orders-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const anomalyPage = {
  items: [{ row_id: 1, anomaly_no: "DEMO-ANOM-001", order_no: "ORD-001", driver_id: "DRIVER-1", vehicle_id: "VEHICLE-1", route_id: "ROUTE-1", latest_task_id: "TASK-ANOM-1", anomaly_type: "DELAY", risk: "HIGH", description: "道路封闭导致延误", status: "PROCESSING", reported_at: "2026-08-29T00:00:00Z" }],
  total: 10, next_cursor: "opaque:anomaly:1", provenance: "LIVE" as const,
};
const orderPage = {
  items: [{ row_id: 2, order_no: "DEMO-ORDER-001", status: "RUNNING", driver_id: "DRIVER-1", vehicle_id: "VEHICLE-1", route_id: "ROUTE-1", origin: "青县", destination: "沧州", created_at: "2026-08-29T00:00:00Z", updated_at: "2026-08-29T01:02:03Z", anomaly_count: 2, latest_task_id: "TASK-ORDER-1" }],
  total: 8, next_cursor: "opaque:order:2", provenance: "MIXED" as const,
};

async function render(page: React.ReactNode) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter>{page}</MemoryRouter>); });
  return { container, root };
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

afterEach(() => {
  runtimeConfig.dataMode = "api";
  for (const method of Object.values(workspaceReadApi)) method.mockReset();
  for (const method of Object.values(mockWorkspaceDataHooks)) method.mockClear();
  vi.mocked(useAnomaliesRead).mockClear();
  vi.mocked(useOrdersRead).mockClear();
  document.body.replaceChildren();
});

describe("business pages mode isolation", () => {
  it("renders Mock content without invoking the Task 5 API read hooks", async () => {
    runtimeConfig.dataMode = "mock";

    const anomalies = await render(<AnomaliesPage />);
    const orders = await render(<OrdersPage />);

    expect(anomalies.container.textContent).toContain("当前异常17");
    expect(anomalies.container.textContent).toContain("演示数据");
    expect(orders.container.textContent).toContain("今日运单1,284");
    expect(orders.container.textContent).toContain("演示数据");
    expect(useAnomaliesRead).not.toHaveBeenCalled();
    expect(useOrdersRead).not.toHaveBeenCalled();
  });

  it("keeps API-only state and branches outside both Mock page bodies", () => {
    const forbidden = /apiCursor|apiHistory|selectedApi|apiRead|useAnomaliesRead|useOrdersRead|dataMode ===/g;
    const anomaliesSource = readFileSync(resolve("src/pages/anomalies-page.tsx"), "utf8");
    const ordersSource = readFileSync(resolve("src/pages/orders-page.tsx"), "utf8");
    const anomalyMockBody = anomaliesSource.slice(
      anomaliesSource.indexOf("function MockAnomaliesPage()"),
      anomaliesSource.indexOf("function ApiAnomaliesPage()"),
    );
    const orderMockBody = ordersSource.slice(
      ordersSource.indexOf("function MockOrdersPage()"),
      ordersSource.indexOf("function ApiOrdersPage()"),
    );

    expect(anomalyMockBody.match(forbidden) ?? []).toEqual([]);
    expect(orderMockBody.match(forbidden) ?? []).toEqual([]);
  });
});

describe("business pages API data truth", () => {
  it("renders API anomaly rows, source and page-derived metrics without the not-exposed message", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue(anomalyPage);
    const { container } = await render(<AnomaliesPage />);
    await flush();

    expect(container.textContent).toContain("DEMO-ANOM-001");
    expect(container.textContent).toContain("当前异常10");
    expect(container.textContent).toContain("本页高风险1");
    expect(container.textContent).toContain("实时数据");
    expect(container.textContent).toContain("DRIVER-1");
    expect(container.textContent).toContain("VEHICLE-1");
    expect(container.textContent).toContain("ROUTE-1");
    expect(container.textContent).not.toContain("异常列表接口尚未开放");
    expect(mockWorkspaceDataHooks.useAnomalies).not.toHaveBeenCalled();
  });

  it("sends primitive anomaly filters and advances with the opaque next cursor", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue(anomalyPage);
    const { container } = await render(<AnomaliesPage />);
    await flush();

    const query = container.querySelector('input[placeholder="异常号 / 运单"]') as HTMLInputElement;
    await act(async () => { setInputValue(query, "ORD-001"); });
    await flush();
    expect(workspaceReadApi.getAnomalies).toHaveBeenLastCalledWith({ query: "ORD-001" }, expect.any(AbortSignal));

    const next = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    await act(async () => { next?.click(); });
    await flush();
    expect(workspaceReadApi.getAnomalies).toHaveBeenLastCalledWith({ cursor: "opaque:anomaly:1", query: "ORD-001" }, expect.any(AbortSignal));
  });

  it("keeps anomaly filters recoverable from an empty filtered or next page", async () => {
    workspaceReadApi.getAnomalies.mockImplementation((filters: { cursor?: string; query?: string }) => Promise.resolve(
      filters.cursor || filters.query ? { items: [], total: 10, next_cursor: null, provenance: "LIVE" } : anomalyPage,
    ));
    const { container } = await render(<AnomaliesPage />);
    await flush();

    const query = container.querySelector('input[placeholder="异常号 / 运单"]') as HTMLInputElement;
    await act(async () => { setInputValue(query, "NO-MATCH"); });
    await flush();
    expect(container.textContent).toContain("当前没有异常记录");
    expect(container.querySelector('input[placeholder="异常号 / 运单"]')).not.toBeNull();
    const clearableQuery = container.querySelector('input[placeholder="异常号 / 运单"]') as HTMLInputElement;
    await act(async () => { setInputValue(clearableQuery, ""); });
    await flush();
    expect(container.textContent).toContain("DEMO-ANOM-001");

    const next = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    await act(async () => { next?.click(); });
    await flush();
    expect(container.textContent).toContain("当前没有异常记录");
    expect(container.textContent).toContain("上一页");
    expect(container.textContent).toContain("返回首页");
    const previous = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "上一页");
    await act(async () => { previous?.click(); });
    await flush();
    expect(container.textContent).toContain("DEMO-ANOM-001");
  });

  it("renders a Chinese empty state for a successful empty anomaly page", async () => {
    workspaceReadApi.getAnomalies.mockResolvedValue({ items: [], total: 0, next_cursor: null, provenance: "LIVE" });
    const { container } = await render(<AnomaliesPage />);
    await flush();

    expect(container.textContent).toContain("当前没有异常记录");
    expect(container.textContent).not.toContain("尚未开放");
  });

  it("shows unavailable state and retries the anomaly read", async () => {
    workspaceReadApi.getAnomalies.mockRejectedValueOnce(new ApiError(503, "UNAVAILABLE", "retry later")).mockResolvedValueOnce(anomalyPage);
    const { container } = await render(<AnomaliesPage />);
    await flush();
    expect(container.textContent).toContain("服务暂不可用");

    const retry = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "重试");
    await act(async () => { retry?.click(); });
    await flush();
    expect(container.textContent).toContain("DEMO-ANOM-001");
  });

  it("renders API order rows, source and the bounded total", async () => {
    workspaceReadApi.getOrders.mockResolvedValue(orderPage);
    const { container } = await render(<OrdersPage />);
    await flush();

    expect(container.textContent).toContain("DEMO-ORDER-001");
    expect(container.textContent).toContain("当前运单8");
    expect(container.textContent).toContain("混合数据");
    expect(container.textContent).toContain("异常数");
    expect(container.textContent).toContain("2");
    expect(container.textContent).toContain("2026-08-29T01:02:03Z");
    expect(container.textContent).not.toContain("运单列表接口尚未开放");
    expect(mockWorkspaceDataHooks.useOrders).not.toHaveBeenCalled();
    expect(Array.from(container.querySelectorAll("button")).some((button) => button.textContent === "下一页")).toBe(true);
  });

  it("opens real relationship details and links to the latest dispatch task", async () => {
    workspaceReadApi.getOrders.mockResolvedValue(orderPage);
    workspaceReadApi.getAnomalies.mockResolvedValue(anomalyPage);
    const orders = await render(<OrdersPage />);
    const anomalies = await render(<AnomaliesPage />);
    await flush();

    const orderRow = Array.from(orders.container.querySelectorAll("button")).find((button) => button.textContent === "DEMO-ORDER-001");
    await act(async () => { orderRow?.click(); });
    expect(orders.container.textContent).toContain("关联异常2");
    expect(orders.container.querySelector('a[href="/dispatch/TASK-ORDER-1"]')).not.toBeNull();

    const anomalyRow = Array.from(anomalies.container.querySelectorAll("button")).find((button) => button.textContent === "DEMO-ANOM-001");
    await act(async () => { anomalyRow?.click(); });
    expect(anomalies.container.textContent).toContain("司机DRIVER-1");
    expect(anomalies.container.textContent).toContain("车辆VEHICLE-1");
    expect(anomalies.container.textContent).toContain("路线ROUTE-1");
    expect(anomalies.container.querySelector('a[href="/dispatch/TASK-ANOM-1"]')).not.toBeNull();
  });

  it("sends an order query and advances with the opaque next cursor", async () => {
    workspaceReadApi.getOrders.mockResolvedValue(orderPage);
    const { container } = await render(<OrdersPage />);
    await flush();

    const query = container.querySelector('input[placeholder="运单 / 司机 / 车辆"]') as HTMLInputElement;
    await act(async () => { setInputValue(query, "DRIVER-1"); });
    await flush();
    expect(workspaceReadApi.getOrders).toHaveBeenLastCalledWith({ query: "DRIVER-1" }, expect.any(AbortSignal));

    const next = Array.from(container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    await act(async () => { next?.click(); });
    await flush();
    expect(workspaceReadApi.getOrders).toHaveBeenLastCalledWith({ cursor: "opaque:order:2", query: "DRIVER-1" }, expect.any(AbortSignal));
  });
});
