import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AgentsPage } from "../src/pages/agents-page";
import { describeAgentEvent } from "../src/utils/agent-event";
import { DashboardPage } from "../src/pages/dashboard-page";
import { MemoryPage } from "../src/pages/memory-page";
import { MonitorPage } from "../src/pages/monitor-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<MemoryRouter>{element}</MemoryRouter>);
    await Promise.resolve();
    await Promise.resolve();
  });
  return { root, container };
}

afterEach(() => document.body.replaceChildren());

describe("V2 product surfaces", () => {
  it("summarizes V2 capabilities and labels acceptance evidence on Dashboard", async () => {
    const { container } = await render(<DashboardPage />);

    expect(container.textContent).toContain("V2 能力总览");
    expect(container.textContent).toContain("8 个智能体");
    expect(container.textContent).toContain("图记忆");
    expect(container.textContent).toContain("共享记忆");
    expect(container.textContent).toContain("已通过验收");
    expect(container.textContent).not.toContain("VERIFIED ACCEPTANCE");
  });

  it("shows the canonical eight-agent order and identifies demo execution data", async () => {
    const { container } = await render(<AgentsPage />);
    const labels = [...container.querySelectorAll(".agent-rail-item strong")].map((node) => node.textContent);

    expect(labels).toEqual([
      "接入智能体", "实体记忆智能体", "图记忆智能体", "环境智能体",
      "运力智能体", "路径智能体", "调度智能体", "审核智能体",
    ]);
    expect(container.textContent).toContain("演示数据");
    expect(container.textContent).toContain("故障降级");
  });

  it("summarizes live agent evidence without rendering raw event JSON", () => {
    const detail = describeAgentEvent("graph_memory", "GRAPH_MEMORY_COMPLETED", {
      graph_memory_facts: [{ relation_type: "DRIVES" }, { relation_type: "HAS_RISK_ON" }],
      graph_memory_paths: [{ hop_count: 2 }],
      noisy_internal_payload: "x".repeat(2_000),
    });

    expect(detail).toBe("GRAPH_MEMORY_COMPLETED · 2 条事实 · 1 条路径");
    expect(detail).not.toContain("noisy_internal_payload");
  });

  it("provides Vector, Graph, and Shared Control tabs with an interactive graph path", async () => {
    const { container } = await render(<MemoryPage />);
    const tabs = [...container.querySelectorAll('[role="tab"]')];
    expect(tabs.map((tab) => tab.textContent)).toEqual(["向量记忆", "图记忆", "共享控制"]);

    await act(async () => { (tabs[1] as HTMLButtonElement).click(); });
    expect(container.textContent).toContain("实体关系图");
    expect(container.textContent).toContain("存在风险");
    expect(container.textContent).toContain("路径检查");
    expect(container.textContent).toContain("跳数");
    expect(container.textContent).toContain("投影已生效");

    const driver = container.querySelector('button[aria-label="选择图节点 李师傅"]') as HTMLButtonElement;
    await act(async () => { driver.click(); });
    expect(container.textContent).toContain("driver-li");

    await act(async () => { (tabs[2] as HTMLButtonElement).click(); });
    expect(container.textContent).toContain("规范事实");
    expect(container.textContent).toContain("演示数据");
    expect(container.textContent).toContain("暂存 · 未生效");
    expect(container.textContent).toContain("记忆变更历史");
  });

  it("fills the monitoring surface with clearly labeled demo metrics when live values are missing", async () => {
    const { container } = await render(<MonitorPage />);

    expect(container.textContent).toContain("演示数据");
    expect(container.textContent).toContain("当前 QPS0.32");
    expect(container.textContent).toContain("智能体 P95238 ms");
    expect(container.textContent).toContain("干预应用率96.7%");
  });

  it("separates live health availability from verified V2 baselines", async () => {
    const { container } = await render(<MonitorPage />);

    for (const service of ["Backend", "Worker-1", "Worker-2", "Redis", "MySQL", "Qdrant", "Neo4j"]) {
      expect(container.textContent).toContain(service);
    }
    expect(container.textContent).toContain("已通过验收");
    expect(container.textContent).toContain("QPS ≥ 400.071");
    expect(container.textContent).toContain("非实时监控");
  });
});
