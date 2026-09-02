import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../src/services/api/client";
import type { MemoryRecord } from "../src/mocks/workspace-data";

const workspaceReadApi = vi.hoisted(() => ({ getVectorMemories: vi.fn() }));
const workspaceDataHooks = vi.hoisted(() => ({
  useMemories: vi.fn((): MemoryRecord[] => []),
  useMemoryControlPlane: vi.fn(() => ({ loading: false, error: null, data: null })),
}));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api", apiBaseUrl: "http://api.test", authenticationMode: "development_jwt" },
}));
vi.mock("../src/services/api/workspace-read-client", () => ({ workspaceReadClient: workspaceReadApi }));
vi.mock("../src/hooks/use-workspace-data", () => workspaceDataHooks);
vi.mock("../src/hooks/use-workspace-reads", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/hooks/use-workspace-reads")>();
  return { ...actual, useVectorMemoriesRead: vi.fn(actual.useVectorMemoriesRead) };
});

import { runtimeConfig } from "../src/config/runtime";
import { useVectorMemoriesRead } from "../src/hooks/use-workspace-reads";
import { MemoryPage } from "../src/pages/memory-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const firstPage = {
  items: [{
    memory_id: "memory-rain-li",
    driver_id: "driver-li",
    route_id: "route-102",
    anomaly_type: "RAIN_SLIPPERY",
    historical_resolution: "建议改走102国道",
    created_at: "2026-08-29T00:00:00Z",
    projection_status: "ACTIVE",
    vector: ["SENSITIVE-VECTOR-VALUE"],
  }],
  total: 2,
  next_cursor: "opaque:memory:1",
  vector_dimension: 128,
  provenance: "LIVE" as const,
};

async function renderMemory(controlFactKey = "") {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(<MemoryRouter><MemoryPage controlFactKey={controlFactKey} /></MemoryRouter>); });
  await flush();
  return { container, root };
}

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

async function click(button: HTMLButtonElement) {
  await act(async () => { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
  await flush();
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

afterEach(() => {
  runtimeConfig.dataMode = "api";
  workspaceReadApi.getVectorMemories.mockReset();
  workspaceDataHooks.useMemories.mockClear();
  workspaceDataHooks.useMemoryControlPlane.mockClear();
  vi.mocked(useVectorMemoriesRead).mockClear();
  document.body.replaceChildren();
});

describe("vector memory API list", () => {
  it("renders current Qdrant metadata and safe row fields without fixed acceptance evidence or vectors", async () => {
    workspaceReadApi.getVectorMemories.mockResolvedValue(firstPage);

    const view = await renderMemory();

    expect(view.container.textContent).toContain("记忆总数2");
    expect(view.container.textContent).toContain("向量维度128");
    expect(Array.from(view.container.querySelectorAll(".source-label")).some((label) => label.textContent === "实时数据")).toBe(true);
    expect(view.container.textContent).toContain("memory-rain-li");
    expect(view.container.textContent).toContain("driver-li");
    expect(view.container.textContent).toContain("route-102");
    expect(view.container.textContent).toContain("RAIN_SLIPPERY");
    expect(view.container.textContent).toContain("建议改走102国道");
    expect(view.container.textContent).toContain("2026-08-29T00:00:00Z");
    expect(view.container.textContent).not.toMatch(/2560|SiliconFlow|49 \/ 50|50 \/ 50/);
    expect(view.container.textContent).not.toContain("当前后端未暴露向量记忆浏览 API");
    expect(view.container.textContent).not.toContain("SENSITIVE-VECTOR-VALUE");
    expect(workspaceDataHooks.useMemories).not.toHaveBeenCalled();
  });

  it.each([
    ["MIXED", "混合数据"],
    ["DEMO", "演示数据"],
  ] as const)("localizes the %s provenance badge", async (provenance, label) => {
    workspaceReadApi.getVectorMemories.mockResolvedValue({ ...firstPage, provenance });

    const view = await renderMemory();

    expect(Array.from(view.container.querySelectorAll(".source-label")).some((source) => source.textContent === label)).toBe(true);
  });

  it("filters the current safe rows and opens a DTO-only detail drawer", async () => {
    workspaceReadApi.getVectorMemories.mockResolvedValue({
      ...firstPage,
      items: [
        firstPage.items[0],
        { ...firstPage.items[0], memory_id: "memory-engine-spare", driver_id: "driver-zhang", historical_resolution: "更换备用车辆" },
      ],
    });
    const view = await renderMemory();

    const query = view.container.querySelector('input[placeholder="记忆 ID / 司机 / 路线 / 异常 / 解决方案"]') as HTMLInputElement;
    expect(query).not.toBeNull();
    await act(async () => { setInputValue(query, "driver-zhang"); });
    expect(view.container.textContent).not.toContain("memory-rain-li");
    expect(view.container.textContent).toContain("memory-engine-spare");

    const detail = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "memory-engine-spare");
    await click(detail!);
    expect(document.body.textContent).toContain("记忆详情");
    expect(document.body.textContent).toContain("driver-zhang");
    expect(document.body.textContent).toContain("更换备用车辆");
    expect(document.body.textContent).not.toContain("SENSITIVE-VECTOR-VALUE");
  });

  it("recovers from an empty cursor page through previous and home controls", async () => {
    workspaceReadApi.getVectorMemories
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce({ items: [], total: 2, next_cursor: null, vector_dimension: 64, provenance: "DEMO" })
      .mockResolvedValueOnce(firstPage);
    const view = await renderMemory();

    const next = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "下一页");
    await click(next!);
    expect(view.container.textContent).toContain("当前页没有向量记忆");
    expect(view.container.textContent).toContain("记忆总数2");
    expect(view.container.textContent).toContain("向量维度64");
    expect(Array.from(view.container.querySelectorAll(".source-label")).some((source) => source.textContent === "演示数据")).toBe(true);
    expect(view.container.textContent).toContain("上一页");
    expect(view.container.textContent).toContain("返回首页");

    const home = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "返回首页");
    await click(home!);
    expect(view.container.textContent).toContain("memory-rain-li");
    expect(workspaceReadApi.getVectorMemories).toHaveBeenNthCalledWith(2, { cursor: "opaque:memory:1", limit: 20 }, expect.any(AbortSignal));
    expect(workspaceReadApi.getVectorMemories).toHaveBeenNthCalledWith(3, { limit: 20 }, expect.any(AbortSignal));
  });

  it("renders an empty collection without falling back to demonstration records", async () => {
    workspaceReadApi.getVectorMemories.mockResolvedValue({ items: [], total: 0, next_cursor: null, vector_dimension: 128, provenance: "MIXED" });

    const view = await renderMemory();

    expect(view.container.textContent).toContain("当前没有向量记忆");
    expect(view.container.textContent).toContain("记忆总数0");
    expect(view.container.textContent).toContain("向量维度128");
    expect(Array.from(view.container.querySelectorAll(".source-label")).some((source) => source.textContent === "混合数据")).toBe(true);
    expect(view.container.textContent).not.toContain("memory-rain-li");
    expect(workspaceDataHooks.useMemories).not.toHaveBeenCalled();
  });

  it("renders a localized loading state while the vector read is pending", async () => {
    workspaceReadApi.getVectorMemories.mockReturnValue(new Promise(() => undefined));

    const view = await renderMemory();

    expect(view.container.textContent).toContain("正在加载向量记忆");
  });

  it("shows unavailable state and retries the same real read", async () => {
    workspaceReadApi.getVectorMemories
      .mockRejectedValueOnce(new ApiError(503, "VECTOR_MEMORY_UNAVAILABLE", "retry later"))
      .mockResolvedValueOnce(firstPage);
    const view = await renderMemory();
    expect(view.container.textContent).toContain("向量记忆服务暂不可用");

    const retry = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "重试");
    await click(retry!);
    expect(view.container.textContent).toContain("memory-rain-li");
  });

  it.each([
    [403, "没有查看向量记忆的权限"],
    [500, "向量记忆加载失败"],
  ] as const)("renders the localized %s failure state", async (status, copy) => {
    workspaceReadApi.getVectorMemories.mockRejectedValue(new ApiError(status, "READ_FAILED", "unsafe provider detail"));

    const view = await renderMemory();

    expect(view.container.textContent).toContain(copy);
    expect(view.container.textContent).not.toContain("unsafe provider detail");
  });
});

describe("vector memory mode isolation", () => {
  it("keeps the demonstration vector surface and all memory tabs without invoking the API hook", async () => {
    runtimeConfig.dataMode = "mock";
    workspaceDataHooks.useMemories.mockReturnValue([{
      memoryId: "memory-mock-only",
      entities: "司机 · 路线",
      scenario: "演示异常",
      resolution: "演示解决方案",
      similarity: "90%",
      vectorDimension: 2560,
      adoptedBy: "TASK-MOCK",
      updatedAt: "20:00",
    }]);

    const view = await renderMemory();

    expect(view.container.textContent).toContain("memory-mock-only");
    expect(view.container.textContent).toContain("向量记忆");
    expect(view.container.textContent).toContain("图记忆");
    expect(view.container.textContent).toContain("共享控制");
    expect(useVectorMemoriesRead).not.toHaveBeenCalled();
  });

  it("preserves the Mock shared-control deep link", async () => {
    runtimeConfig.dataMode = "mock";

    const view = await renderMemory("smf_" + "a".repeat(64));

    expect(view.container.textContent).toContain("MySQL · 规范控制平面");
    expect(view.container.textContent).toContain("规范事实");
    expect(view.container.textContent).not.toContain("向量 Top-1");
  });
});
