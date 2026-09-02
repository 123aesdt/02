import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuntimeThreadPanel } from "../src/components/runtime-thread-panel";
import type { RuntimeThreadClient } from "../src/services/api/runtime-thread-client";
import type { RuntimeThreadDetail } from "../src/types/runtime-thread";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const detail: RuntimeThreadDetail = {
  thread_id: "cf:dispatch:TASK-1",
  task_id: "TASK-1",
  status: "STABLE",
  terminal: false,
  current_checkpoint_id: "checkpoint-2",
  state_version: 2,
  current_node: "entity_memory",
  next_node: "graph_memory",
  checkpoint_count: 2,
  checkpoint_size_bytes: 845,
  last_event_sequence: 7,
  worker_consumer: "worker-county-02",
  checkpoint_available: true,
  state: { last_completed_node: "entity_memory" },
  created_at: "2026-08-27T00:00:00Z",
  updated_at: "2026-08-27T00:00:01Z",
  terminal_at: null,
};

function client(overrides: Partial<RuntimeThreadClient> = {}): RuntimeThreadClient {
  return {
    getByTask: vi.fn().mockResolvedValue(detail),
    getHistory: vi.fn().mockResolvedValue({
      thread_id: detail.thread_id,
      items: [
        { checkpoint_id: "checkpoint-2", state_version: 2, node: "entity_memory", checkpoint_available: true },
        { checkpoint_id: "checkpoint-1", state_version: 1, node: "intake", checkpoint_available: true },
      ],
    }),
    ...overrides,
  };
}

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  return { root, container };
}

async function flush(): Promise<void> {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
}

afterEach(() => document.body.replaceChildren());

describe("RuntimeThreadPanel", () => {
  it("stays hidden when the feature is disabled", async () => {
    const { container } = await render(<RuntimeThreadPanel taskId="TASK-1" enabled={false} client={client()} />);
    expect(container.textContent).toBe("");
  });

  it("reloads checkpoint state when the task refresh key changes", async () => {
    const api = client();
    const view = await render(<RuntimeThreadPanel taskId="TASK-1" enabled client={api} refreshKey={0} />);
    await flush();
    expect(api.getByTask).toHaveBeenCalledTimes(1);

    await act(async () => {
      view.root.render(<RuntimeThreadPanel taskId="TASK-1" enabled client={api} refreshKey={1} />);
    });

    await flush();
    expect(api.getByTask).toHaveBeenCalledTimes(2);
  });

  it("renders canonical state and bounded history without mutation controls", async () => {
    const api = client();
    const { container } = await render(<RuntimeThreadPanel taskId="TASK-1" enabled client={api} />);
    await flush();

    expect(container.textContent).toContain("运行线程");
    expect(container.textContent).toContain("cf:dispatch:TASK-1");
    expect(container.textContent).toContain("checkpoint-2");
    expect(container.textContent).toContain("entity_memory → graph_memory");
    expect(container.textContent).toContain("worker-county-02");
    expect(container.textContent).toContain("2026-08-27T00:00:01Z");
    expect(container.textContent).toContain("检查点状态版本 2");
    expect(api.getHistory).toHaveBeenCalledWith(detail.thread_id, 20, expect.any(AbortSignal));
    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(container.textContent?.toLowerCase()).not.toMatch(/pause|resume|rollback|override/);
  });

  it("shows expired and unauthorized states", async () => {
    const expired = client({ getByTask: vi.fn().mockResolvedValue({ ...detail, checkpoint_available: false, state: null }) });
    const first = await render(<RuntimeThreadPanel taskId="TASK-1" enabled client={expired} />);
    await flush();
    expect(first.container.textContent).toContain("检查点已过期或不可用");
    await act(async () => { first.root.unmount(); });

    const unauthorized = client({ getByTask: vi.fn().mockRejectedValue(Object.assign(new Error("forbidden"), { status: 403 })) });
    const second = await render(<RuntimeThreadPanel taskId="TASK-1" enabled client={unauthorized} />);
    await flush();
    expect(second.container.textContent).toContain("无权查看运行线程");
  });
});
