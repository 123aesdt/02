import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "../src/pages/login/login-page";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const employees = [
  { employee_id: "CF-DEMO-001", display_name: "张师傅", role: "EMPLOYEE" as const },
  { employee_id: "CF-DEMO-007", display_name: "孙调度", role: "DISPATCHER" as const },
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
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CountyFlow login page", () => {
  it("renders the cinematic account selector with a prefilled demo password", async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined);
    const { root, container } = await render(<LoginPage
      employees={employees}
      loading={false}
      status="anonymous"
      error={null}
      onLogin={onLogin}
    />);

    expect(container.querySelector("[data-county-login]")).not.toBeNull();
    expect(container.querySelector('[data-login-route-layer][data-route-placement="city-corridor"]')).not.toBeNull();
    expect(container.querySelector("[data-login-vehicle]")).toBeNull();
    expect(container.querySelector("[data-login-truck-glow]")).not.toBeNull();
    expect(container.querySelectorAll("[data-login-truck-streak]")).toHaveLength(4);
    expect(container.querySelector("[data-login-road-flow]")).not.toBeNull();
    expect(container.querySelector('img[src="/assets/login/county-valley-logistics-sunrise.png"]')).not.toBeNull();
    expect(container.querySelectorAll("[data-login-particle]").length).toBeLessThanOrEqual(10);
    expect(container.textContent).toContain("县域物流智慧配送平台");
    const accountTab = container.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]');
    const scanTab = container.querySelector<HTMLButtonElement>('[role="tab"][aria-disabled="true"]');
    expect(accountTab?.textContent).toContain("账号登录");
    expect(scanTab?.textContent).toContain("扫码登录");
    expect(container.querySelector<HTMLInputElement>('input[aria-label="记住当前账号"]')?.checked).toBe(true);
    expect(container.querySelector<HTMLButtonElement>('button[aria-label="忘记密码"]')?.disabled).toBe(true);
    const password = container.querySelector<HTMLInputElement>('input[aria-label="登录密码"]');
    expect(password?.type).toBe("password");
    expect(password?.value.length).toBeGreaterThan(7);
    expect(password?.readOnly).toBe(true);
    expect(container.querySelector('select[aria-label="切换演示员工"]')).not.toBeNull();

    const button = container.querySelector<HTMLButtonElement>('button[type="submit"]');
    expect(button?.disabled).toBe(false);
    await act(async () => { root.unmount(); });
  });

  it("submits the selected employee through the existing authentication callback", async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined);
    const { root, container } = await render(<LoginPage
      employees={employees}
      loading={false}
      status="anonymous"
      error={null}
      onLogin={onLogin}
    />);
    const select = container.querySelector<HTMLSelectElement>('select[aria-label="切换演示员工"]');
    if (!select) throw new Error("missing employee selector");

    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set?.call(select, "CF-DEMO-007");
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => { container.querySelector<HTMLButtonElement>('button[type="submit"]')?.click(); });

    expect(onLogin).toHaveBeenCalledOnce();
    expect(onLogin).toHaveBeenCalledWith("CF-DEMO-007");
    await act(async () => { root.unmount(); });
  });

  it("uses one animation-frame loop for parallax and cancels it on unmount", async () => {
    let pendingFrame: FrameRequestCallback | null = null;
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      pendingFrame = callback;
      return 73;
    });
    const cancelFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestFrame);
    vi.stubGlobal("cancelAnimationFrame", cancelFrame);
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));

    const { root, container } = await render(<LoginPage
      employees={employees}
      loading={false}
      status="anonymous"
      error={null}
      onLogin={vi.fn()}
    />);
    const page = container.querySelector<HTMLElement>("[data-county-login]");
    page?.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 900, clientY: 300 }));
    expect(requestFrame).toHaveBeenCalledOnce();
    if (!pendingFrame) throw new Error("missing animation frame");
    (pendingFrame as FrameRequestCallback)(16);
    expect(page?.style.getPropertyValue("--login-parallax-x")).not.toBe("");

    await act(async () => { root.unmount(); });
    expect(cancelFrame).toHaveBeenCalled();
  });
});
