import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DevRolePreview, isDevRolePreviewEnabled } from "../src/auth/dev-role-preview";

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

describe("server-issued development role preview", () => {
  it("test_production_no_role_switcher", async () => {
    const view = await render(<DevRolePreview enabled={false} currentRole="ADMIN" onSelect={vi.fn()} />);
    expect(view.container.textContent).not.toContain("开发角色预览");
    expect(isDevRolePreviewEnabled({ isDevelopmentBuild: false, dataMode: "api", authenticationMode: "development_jwt" })).toBe(false);
  });

  it("test_dev_role_preview_marked", async () => {
    const view = await render(<DevRolePreview enabled currentRole="DISPATCHER" onSelect={vi.fn()} />);
    expect(view.container.textContent).toContain("开发角色预览");
    expect([...view.container.querySelectorAll("option")].map((option) => option.value)).toEqual([
      "EMPLOYEE", "DISPATCHER", "SUPERVISOR", "OPERATOR", "AUDITOR", "ADMIN",
    ]);
  });

  it("requests a new server identity and never constructs permissions in the browser", async () => {
    const onSelect = vi.fn(async () => undefined);
    const view = await render(<DevRolePreview enabled currentRole="DISPATCHER" onSelect={onSelect} />);
    const select = view.container.querySelector("select") as HTMLSelectElement;

    await act(async () => {
      select.value = "AUDITOR";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });

    expect(onSelect).toHaveBeenCalledWith("AUDITOR");
    const previewSource = readFileSync(resolve("src/auth/dev-role-preview.tsx"), "utf8");
    const providerSource = readFileSync(resolve("src/auth/auth-provider.tsx"), "utf8");
    expect(previewSource + providerSource).not.toContain("permissionsForRole");
    expect(previewSource + providerSource).not.toMatch(/localStorage|sessionStorage/);
  });
});
