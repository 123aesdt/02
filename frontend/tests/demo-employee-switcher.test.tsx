import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DemoEmployeeSwitcher } from "../src/auth/demo-employee-switcher";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const employees = [
  { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" as const },
  { employee_id: "CF-DEMO-003", display_name: "王主管", role: "SUPERVISOR" as const },
  { employee_id: "CF-DEMO-005", display_name: "系统管理员", role: "ADMIN" as const },
];

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

describe("demo employee switcher", () => {
  it("renders Chinese employee and role labels without a password input", async () => {
    const view = await render(<DemoEmployeeSwitcher
      enabled
      employees={employees}
      currentEmployeeId={null}
      onSelect={vi.fn()}
    />);

    const select = view.container.querySelector("select") as HTMLSelectElement;
    expect(select.getAttribute("aria-label")).toBe("切换演示员工");
    expect(view.container.textContent).toContain("演示身份");
    expect(view.container.textContent).toContain("张师傅 · 配送员工");
    expect(view.container.querySelector('input[type="password"]')).toBeNull();
  });

  it("requests the selected employee id and disables selection while pending", async () => {
    const onSelect = vi.fn(async () => undefined);
    const view = await render(<DemoEmployeeSwitcher
      enabled
      employees={employees}
      currentEmployeeId="CF-DEMO-001"
      pending
      onSelect={onSelect}
    />);
    const select = view.container.querySelector("select") as HTMLSelectElement;
    expect(select.disabled).toBe(true);

    await act(async () => {
      select.disabled = false;
      select.value = "CF-DEMO-003";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });

    expect(onSelect).toHaveBeenCalledWith("CF-DEMO-003");
  });

  it("stays hidden when the backend is not in demo employee mode", async () => {
    const view = await render(<DemoEmployeeSwitcher
      enabled={false}
      employees={employees}
      currentEmployeeId={null}
      onSelect={vi.fn()}
    />);
    expect(view.container.querySelector("select")).toBeNull();
  });
});
