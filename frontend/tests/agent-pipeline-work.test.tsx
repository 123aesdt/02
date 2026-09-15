import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { AgentPipeline } from "../src/components/agent-pipeline";
import { dashboardSnapshot } from "../src/mocks/dispatch-data";
import type { AgentRun } from "../src/types/dispatch";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type WorkAwareAgent = AgentRun & {
  work: {
    input: string;
    action: string;
    result: string;
    evidence: Array<{ label: string; value: string }>;
    eventType: string;
    eventId: string;
  };
};

const routingAgent: WorkAwareAgent = {
  id: "routing",
  name: "路径智能体",
  status: "SUCCESS",
  elapsed: "31 ms",
  output: "已避开 E04，推荐 RTE-F2DD2BEA7BC56B05",
  detail: "ROUTING_COMPLETED",
  work: {
    input: "阻断道路 E04、当前路线和车辆约束",
    action: "比较候选路线并检查道路连通性",
    result: "已避开 E04，推荐 RTE-F2DD2BEA7BC56B05",
    evidence: [
      { label: "算法", value: "Dijkstra" },
      { label: "推荐路线", value: "RTE-F2DD2BEA7BC56B05" },
    ],
    eventType: "ROUTING_COMPLETED",
    eventId: "event-routing-1",
  },
};

async function render(agents: AgentRun[]): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<AgentPipeline agents={agents} />); });
  return { root, container };
}

afterEach(() => document.body.replaceChildren());

describe("AgentPipeline work details", () => {
  it("keeps all eight demo agents ready for an offline live demonstration", () => {
    expect(dashboardSnapshot.agents).toHaveLength(8);
    expect(dashboardSnapshot.agents.every((agent) => agent.work?.input && agent.work.action && agent.work.result)).toBe(true);
  });

  it("keeps a readable result visible and expands the real work evidence", async () => {
    const { root, container } = await render([routingAgent]);

    expect(container.textContent).toContain("已避开 E04，推荐 RTE-F2DD2BEA7BC56B05");
    expect(container.textContent).not.toContain('{"recommended_route"');
    const toggle = container.querySelector('button[aria-label="查看路径智能体工作详情"]') as HTMLButtonElement;
    expect(toggle).not.toBeNull();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await act(async () => { toggle.click(); });

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(container.textContent).toContain("读取信息");
    expect(container.textContent).toContain("阻断道路 E04、当前路线和车辆约束");
    expect(container.textContent).toContain("执行动作");
    expect(container.textContent).toContain("比较候选路线并检查道路连通性");
    expect(container.textContent).toContain("输出结果");
    expect(container.textContent).toContain("关键证据");
    expect(container.textContent).toContain("event-routing-1");
    await act(async () => { root.unmount(); });
  });

  it("opens a failed agent first so the blocking reason is immediately visible", async () => {
    const failedAgent: WorkAwareAgent = {
      ...routingAgent,
      id: "audit",
      name: "审核智能体",
      status: "FAILED",
      output: "未找到可连通路线，需要人工复核",
      work: { ...routingAgent.work, result: "未找到可连通路线，需要人工复核" },
    };
    const { root, container } = await render([routingAgent, failedAgent]);

    const toggles = [...container.querySelectorAll<HTMLButtonElement>(".pipeline-work-toggle")];
    expect(toggles[0].getAttribute("aria-expanded")).toBe("false");
    expect(toggles[1].getAttribute("aria-expanded")).toBe("true");
    await act(async () => { root.unmount(); });
  });
});
