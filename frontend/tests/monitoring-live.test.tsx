import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { LiveObservabilityPanel } from "../src/components/live-observability-panel";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function renderPanel(state: "LIVE" | "STALE" | "UNAVAILABLE" | "NO_PERMISSION", demoFallback = false) {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<LiveObservabilityPanel
    state={state}
    demoFallback={demoFallback}
    window="5m"
    onWindowChange={() => undefined}
    data={state === "LIVE" ? {
      state: "LIVE", window: "5m", timestamp: "2026-08-28T00:00:00Z",
      metrics: { http_qps: 12.5, http_p95: 0.12, worker_pending: 0, graph_p95: 0.01, dependency_up: 0 },
      series: { dependency_up: { mysql: 1, redis: 1, qdrant: 1, neo4j: 0 } },
      grafana_url: "http://localhost:3000",
    } : null}
  />));
  return container;
}

afterEach(() => document.body.replaceChildren());

describe("live monitoring", () => {
  it("test_frontend_verified_baseline_separate", async () => {
    const container = await renderPanel("LIVE");
    expect(container.textContent).toContain("实时可观测性");
    expect(container.textContent).not.toContain("已通过验收");
  });

  it("test_frontend_observability_unavailable", async () => {
    const container = await renderPanel("UNAVAILABLE");
    expect(container.textContent).toContain("监控暂不可用");
    expect(container.textContent).not.toContain("演示数据");
  });

  it("shows a bounded dependency failure without replacing live data", async () => {
    const container = await renderPanel("LIVE");
    expect(container.textContent).toContain("Neo4j 异常");
    expect(container.textContent).toContain("MySQL 正常");
  });

  it("fills only missing metrics when the operations surface explicitly enables demo fallback", async () => {
    const container = await renderPanel("LIVE", true);

    expect(container.textContent).toContain("当前 QPS12.50");
    expect(container.textContent).toContain("智能体 P95238 ms");
    expect(container.textContent).toContain("混合数据");
    expect(container.textContent).toContain("演示");
    expect(container.textContent).toContain("Neo4j 异常");
  });

  it("shows an explicitly labeled metric snapshot when live monitoring is unavailable", async () => {
    const container = await renderPanel("UNAVAILABLE", true);

    expect(container.textContent).toContain("监控暂不可用");
    expect(container.textContent).toContain("演示数据");
    expect(container.textContent).toContain("当前 QPS0.32");
    expect(container.textContent).not.toContain("MySQL 正常");
  });
});
