import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthContext, type AuthContextValue } from "../src/auth/auth-state";

const dispatchApi = vi.hoisted(() => ({ createDispatchTask: vi.fn() }));

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: { dataMode: "api" },
}));
vi.mock("../src/services/dispatch-service", () => dispatchApi);

import { DispatchSubmissionButton } from "../src/components/dispatch-submission-button";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const auth: AuthContextValue = {
  status: "authenticated",
  principal: null,
  permissions: ["dispatch:create"],
  error: null,
  demoEmployees: [
    { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" },
    { employee_id: "CF-DEMO-003", display_name: "王主管", role: "SUPERVISOR" },
    { employee_id: "CF-DEMO-006", display_name: "陈师傅", role: "EMPLOYEE" },
    { employee_id: "CF-DEMO-007", display_name: "孙调度", role: "DISPATCHER" },
  ],
  demoEmployeesLoading: false,
  logout: vi.fn(),
  switchDemoEmployee: vi.fn(),
};

async function render(): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <DispatchSubmissionButton />
        </AuthContext.Provider>
      </MemoryRouter>,
    );
  });
  return { root, container };
}

afterEach(() => {
  dispatchApi.createDispatchTask.mockReset();
  document.body.replaceChildren();
});

describe("dispatch recipient", () => {
  it("submits the selected delivery employee and excludes dispatchers", async () => {
    dispatchApi.createDispatchTask.mockResolvedValue({ task_id: "TASK-server-1" });
    const { root, container } = await render();
    const select = container.querySelector<HTMLSelectElement>('select[aria-label="接收员工"]');

    expect(select).not.toBeNull();
    expect([...select!.options].map((option) => option.textContent)).toEqual(["张师傅 · 配送员工", "陈师傅 · 配送员工"]);
    await act(async () => {
      select!.value = "CF-DEMO-006";
      select!.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const button = [...container.querySelectorAll<HTMLButtonElement>("button")]
      .find((item) => item.textContent?.includes("发起 AI 调度"));
    await act(async () => {
      button?.click();
      await Promise.resolve();
    });

    expect(dispatchApi.createDispatchTask).toHaveBeenCalledWith(expect.objectContaining({
      assignee_employee_id: "CF-DEMO-006",
    }));
    await act(async () => { root.unmount(); });
  });
});
