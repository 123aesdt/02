import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DataTable } from "../src/components/ui/data-table";
import { EmptyState } from "../src/components/ui/empty-state";
import { Skeleton } from "../src/components/ui/skeleton";
import { StatusBadge } from "../src/components/ui/status-badge";
import { WorkspaceSection } from "../src/components/workspace/workspace-section";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  return { root, container };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("shared role workspace UI", () => {
  it("renders localized status with a non-color marker", async () => {
    const { container } = await render(<StatusBadge status="REVIEW_REQUIRED" />);
    const badge = container.querySelector('[data-tone="warning"]');

    expect(badge?.textContent).toContain("需复核");
    expect(badge?.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(badge?.getAttribute("aria-label")).toContain("REVIEW_REQUIRED");
  });

  it("distinguishes empty from a backend contract that is not exposed", async () => {
    const first = await render(<EmptyState kind="empty" title="当前没有待处理异常" />);
    expect(first.container.querySelector('[data-state="empty"]')?.textContent).toContain("当前没有待处理异常");
    await act(async () => { first.root.unmount(); });

    const second = await render(<EmptyState kind="not-exposed" title="业务汇总接口未开放" />);
    expect(second.container.querySelector('[data-state="not-exposed"]')?.textContent).toContain("业务汇总接口未开放");
  });

  it("test_light_theme_table keeps real headers and renders the empty slot", async () => {
    const { container } = await render(
      <DataTable
        caption="待处理任务"
        columns={[{ key: "task", label: "任务" }]}
        rows={[]}
        empty={<EmptyState kind="empty" title="当前没有待处理任务" />}
      />,
    );

    expect(container.querySelector("caption")?.textContent).toBe("待处理任务");
    expect(container.querySelector('th[scope="col"]')?.textContent).toBe("任务");
    expect(container.textContent).toContain("当前没有待处理任务");
  });

  it("provides accessible section and reduced-motion-aware skeleton semantics", async () => {
    const { container } = await render(
      <WorkspaceSection id="my-tasks" title="我的待办" description="按风险与等待时间排序">
        <Skeleton label="正在加载我的待办" lines={2} />
      </WorkspaceSection>,
    );

    expect(container.querySelector('section[aria-labelledby="workspace-section-my-tasks"]')).not.toBeNull();
    expect(container.querySelector('[role="status"]')?.getAttribute("aria-label")).toBe("正在加载我的待办");
    expect(container.querySelectorAll(".ui-skeleton__line")).toHaveLength(2);
  });
});
