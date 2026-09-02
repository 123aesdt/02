import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const testRuntime = vi.hoisted(() => ({
  dataMode: "api" as "api" | "mock",
  authenticationMode: "development_jwt" as "development_jwt" | "oidc_jwt",
}));

vi.mock("../src/config/runtime", () => ({ runtimeConfig: testRuntime }));
vi.mock("../src/hooks/use-task-events", () => ({
  useTaskEvents: () => ({
    connection: "DISCONNECTED",
    events: [],
    agents: [
      "intake", "entity_memory", "graph_memory", "environment",
      "capacity", "routing", "dispatch", "audit",
    ].map((id) => ({ id, status: "WAITING" })),
  }),
}));

import { AgentsPage } from "../src/pages/agents-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function renderAgents() {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><AgentsPage /></MemoryRouter>); });
  return { container, root };
}

afterEach(() => {
  testRuntime.dataMode = "api";
  testRuntime.authenticationMode = "development_jwt";
  document.body.replaceChildren();
});

describe("agent demo snapshot fallback", () => {
  it("shows a labeled eight-agent snapshot until a real task ID is entered", async () => {
    const view = await renderAgents();

    expect(view.container.textContent).toContain("DEMO-TASK-001");
    expect(view.container.textContent).toContain("演示数据");
    expect(view.container.textContent).toContain("18 ms");
    expect(view.container.textContent).toContain("5 条有界关系事实");

    const input = view.container.querySelector('input[placeholder="TASK-..."]') as HTMLInputElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, "TASK-LIVE-9");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });

    expect(view.container.textContent).toContain("TASK-LIVE-9");
    expect(view.container.textContent).toContain("等待真实任务事件");
    expect(view.container.textContent).toContain("后端 WebSocket");
    expect(view.container.textContent).not.toContain("DEMO-TASK-001");
  });

  it("does not show the virtual execution to an OIDC runtime", async () => {
    testRuntime.authenticationMode = "oidc_jwt";
    const view = await renderAgents();

    expect(view.container.textContent).toContain("等待任务 ID");
    expect(view.container.textContent).toContain("等待真实任务事件");
    expect(view.container.textContent).not.toContain("DEMO-TASK-001");
  });
});
