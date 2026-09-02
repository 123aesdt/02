import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

const memoryApi = vi.hoisted(() => ({ getMemoryFact: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test" },
}));
vi.mock("../src/services/api/memory-client", () => memoryApi);

import { MemoryPage } from "../src/pages/memory-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function render(): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <MemoryPage controlFactKey={"smf_" + "a".repeat(64)} />
      </MemoryRouter>,
    );
  });
  await act(async () => { await Promise.resolve(); });
  return { root, container };
}

afterEach(() => {
  memoryApi.getMemoryFact.mockReset();
  document.body.replaceChildren();
});

it("keeps the shared control tab independent from the vector read surface", async () => {
  memoryApi.getMemoryFact.mockResolvedValue(null);

  const { root, container } = await render();

  expect(container.textContent).toContain("共享控制");
  expect(container.textContent).toContain("MySQL · 规范控制平面");
  await act(async () => { root.unmount(); });
});

it("shows clearly labeled demo graph evidence while no API task is selected", async () => {
  memoryApi.getMemoryFact.mockResolvedValue(null);

  const { root, container } = await render();
  const graphTab = [...container.querySelectorAll('[role="tab"]')]
    .find((tab) => tab.textContent === "图记忆") as HTMLButtonElement;
  await act(async () => { graphTab.click(); });

  expect(container.textContent).toContain("演示数据");
  expect(container.textContent).toContain("李师傅");
  expect(container.textContent).toContain("存在风险");
  expect(container.textContent).toContain("路径检查");
  await act(async () => { root.unmount(); });
});

it("shows a clearly labeled demo shared fact when the API has no matching fact", async () => {
  memoryApi.getMemoryFact.mockResolvedValue(null);

  const { root, container } = await render();

  expect(container.textContent).toContain("演示数据");
  expect(container.textContent).toContain("smf_vehicle_a_status");
  expect(container.textContent).toContain("mutation-8");
  await act(async () => { root.unmount(); });
});

it("shows canonical version and mutation decisions without enabling unauthenticated approval", async () => {
  memoryApi.getMemoryFact.mockResolvedValue({
    fact_key: "smf_" + "a".repeat(64),
    version: 8,
    confidence: "0.9000",
    status: "ACTIVE",
    expires_at: null,
    value_json: { status: "Broken" },
    projection_incomplete: false,
    mutations: [
      { mutation_id: "mutation-8", decision: "REPLACE", status: "APPLIED", before_version: 7, after_version: 8, vector_status: "ACTIVE", graph_status: "ACTIVE", reason_code: "HUMAN_CONFIRMED", error_code: null, error_summary: null, created_at: "2026-08-27T01:00:00Z" },
      { mutation_id: "mutation-review", decision: "CONFLICT_REVIEW", status: "CONFLICT", before_version: 7, after_version: 7, vector_status: "NOT_REQUIRED", graph_status: "NOT_REQUIRED", reason_code: "CONTENT_CONFLICT_REVIEW", error_code: null, error_summary: null, created_at: "2026-08-27T00:30:00Z" },
    ],
    evidence: [],
  });

  const { root, container } = await render();

  expect(container.textContent).toContain("版本 8");
  expect(container.textContent).toContain("冲突复核");
  expect(container.textContent).toContain("实时 API");
  expect(container.textContent).not.toContain("smf_vehicle_a_status");
  const approval = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("人工确认"));
  expect(approval?.disabled).toBe(true);
  expect(container.textContent).toContain("授权尚未配置");
  await act(async () => { root.unmount(); });
});
