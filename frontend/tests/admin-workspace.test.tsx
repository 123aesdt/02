import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { permissionsForRole } from "../src/auth/permissions";
import { flattenNavigationLabels, resolveNavigation } from "../src/navigation/navigation-resolver";

const workspaceReadApi = vi.hoisted(() => ({ getOverview: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));

import { AdminOverviewPage } from "../src/pages/admin-overview-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function renderAdmin() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><AdminOverviewPage /></MemoryRouter>); });
  return { container, root };
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

afterEach(() => {
  workspaceReadApi.getOverview.mockReset();
  document.body.replaceChildren();
});

describe("Admin workspace", () => {
  it("keeps the complete admin navigation", async () => {
    workspaceReadApi.getOverview.mockResolvedValue({ orders: 12, anomalies: 3, reviews: 2, runtime_threads: 4, provenance: "LIVE" });
    const labels = flattenNavigationLabels(resolveNavigation({ roles: ["ADMIN"], permissions: permissionsForRole("ADMIN") }));
    expect(labels).toEqual(expect.arrayContaining(["系统总览", "异常中心", "智能调度", "智能体中心", "记忆中心", "运行态", "系统监控", "审计中心"]));

    const view = await renderAdmin();
    await flush();
    expect(view.container.querySelector("h1")?.textContent).toBe("系统总览");
    expect(view.container.querySelector("[data-admin-overview-dashboard]")).not.toBeNull();
    expect(view.container.querySelectorAll("[data-overview-kpi]")).toHaveLength(4);
    expect(view.container.querySelectorAll("[data-overview-capability]")).toHaveLength(6);
    expect(view.container.querySelector("[data-overview-footer]")).not.toBeNull();
    expect(Array.from(view.container.querySelectorAll("a")).map((link) => link.textContent)).toEqual([
      "业务健康", "智能体", "记忆", "运行", "可观测性", "治理与安全",
    ]);
    expect(Array.from(view.container.querySelectorAll("a")).map((link) => link.getAttribute("href"))).toEqual([
      "/anomalies", "/agents", "/memory", "/runtime", "/monitor", "/audit",
    ]);
  });

  it("keeps API counts live while filling uncovered capabilities with labeled demo summaries", async () => {
    workspaceReadApi.getOverview.mockResolvedValue({ orders: 12, anomalies: 3, reviews: 2, runtime_threads: 4, provenance: "LIVE" });
    const view = await renderAdmin();
    await flush();

    expect(view.container.textContent).toContain("运单12");
    expect(view.container.textContent).toContain("异常3");
    expect(view.container.textContent).toContain("待复核2");
    expect(view.container.textContent).toContain("运行线程4");
    expect(view.container.querySelector('[data-overview-kpi="orders"]')?.textContent).toContain("12");
    expect(view.container.querySelector('[data-overview-kpi="anomalies"]')?.textContent).toContain("3");
    expect(view.container.querySelector('[data-overview-kpi="reviews"]')?.textContent).toContain("2");
    expect(view.container.querySelector('[data-overview-kpi="runtime"]')?.textContent).toContain("4");
    expect(view.container.textContent).toContain("实时数据");
    expect(view.container.textContent).toContain("实时计数与演示摘要");
    expect(view.container.textContent).toContain("8 个智能体已准备");
    expect(view.container.textContent).toContain("50 条向量验收记录");
    expect(view.container.querySelectorAll(".ui-status-badge")).toHaveLength(6);
    expect(Array.from(view.container.querySelectorAll(".ui-status-badge")).filter((badge) => badge.textContent?.includes("实时数据"))).toHaveLength(2);
    expect(Array.from(view.container.querySelectorAll(".ui-status-badge")).filter((badge) => badge.textContent?.includes("演示数据"))).toHaveLength(4);
    expect(view.container.textContent).not.toContain("待独立数据源");
  });

  it("keeps mixed overview provenance consistent in the badge semantics", async () => {
    workspaceReadApi.getOverview.mockResolvedValue({ orders: 12, anomalies: 3, reviews: 2, runtime_threads: 4, provenance: "MIXED" });
    const view = await renderAdmin();
    await flush();

    const badge = Array.from(view.container.querySelectorAll(".ui-status-badge")).find((item) => item.textContent?.includes("混合数据"));
    expect(badge?.textContent).toContain("混合数据");
    expect(badge?.getAttribute("aria-label")).toContain("MIXED");
    expect(badge?.getAttribute("aria-label")).not.toContain("LIVE");
  });

  it("does not invent an IAM page or percentage metric", async () => {
    workspaceReadApi.getOverview.mockResolvedValue({ orders: 0, anomalies: 0, reviews: 0, runtime_threads: 0, provenance: "LIVE" });
    const view = await renderAdmin();
    await flush();
    expect(view.container.textContent).not.toMatch(/IAM|用户管理|角色管理|租户管理/);
    expect(view.container.textContent).not.toMatch(/\b\d+(?:\.\d+)?%\b/);
  });
});
