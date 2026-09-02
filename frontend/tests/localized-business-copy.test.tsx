import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "mock", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));

import { AnomaliesPage } from "../src/pages/anomalies-page";
import { DashboardPage } from "../src/pages/dashboard-page";
import { DispatchDetailPage } from "../src/pages/dispatch-detail-page";
import { OrdersPage } from "../src/pages/orders-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function render(page: React.ReactNode): Promise<HTMLDivElement> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter>{page}</MemoryRouter>); });
  return container;
}

afterEach(() => document.body.replaceChildren());

it("uses Chinese copy on mock dashboard and business lists", async () => {
  const dashboard = await render(<DashboardPage />);
  expect(dashboard.textContent).toContain("演示数据");
  expect(dashboard.textContent).toContain("高");
  expect(dashboard.textContent).not.toMatch(/DEMO DATA|LIVE API MODE|Entity Memory|Graph Memory|Static Route Rule|Primary Timeout/);

  const anomalies = await render(<AnomaliesPage />);
  expect(anomalies.textContent).toContain("异常工作台");
  expect(anomalies.textContent).toContain("已降级");
  expect(anomalies.textContent).not.toMatch(/EXCEPTION DESK|DEMO 数据|Environment|Memory|APPROVED|HIGH|MEDIUM|LOW/);

  const orders = await render(<OrdersPage />);
  expect(orders.textContent).toContain("运单运营");
  expect(orders.textContent).not.toMatch(/ORDER OPERATIONS|DEMO 数据|Fallback/);
});

it("uses Chinese copy throughout mock dispatch detail", async () => {
  const container = await render(<DispatchDetailPage />);
  expect(container.textContent).toContain("异常上下文");
  expect(container.textContent).toContain("实体记忆证据");
  expect(container.textContent).toContain("调度结果");
  expect(container.textContent).toContain("暴雨");
  expect(container.textContent).not.toMatch(/ANOMALY CONTEXT|ENVIRONMENT|CAPACITY|ROUTE DECISION|DECISION EXPLANATION|ENTITY MEMORY EVIDENCE|GRAPH MEMORY EVIDENCE|FINAL AUDIT|DISPATCH RESULT|Heavy Rain|Slippery|Static Route Rule|Score|YES|NO/);
});
