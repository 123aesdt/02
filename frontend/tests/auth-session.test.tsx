import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../src/auth/auth-provider";
import { useAuth } from "../src/auth/auth-state";
import { AuthSessionBanner } from "../src/auth/auth-session-banner";
import { PermissionGate } from "../src/auth/permission-gate";
import {
  clearSession,
  getSessionSnapshot,
  setAuthenticatedSession,
} from "../src/auth/session";
import { createApiClient } from "../src/services/api/client";
import { PERMISSIONS, permissionsForRole } from "../src/auth/permissions";

vi.mock("../src/config/runtime", () => ({
  runtimeConfig: {
    dataMode: "api",
    apiBaseUrl: "http://api.test",
    authenticationMode: "development_jwt",
    runtimeThreadStateEnabled: true,
  },
}));

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const principal = {
  subject_id: "operator-1",
  display_name: "Operator One",
  roles: ["OPERATOR"],
  permissions: ["monitor:read", "runtime:read"],
  auth_method: "development_jwt" as const,
  issued_at: new Date(Date.now() - 1_000).toISOString(),
  expires_at: new Date(Date.now() + 600_000).toISOString(),
};

async function render(element: React.ReactNode): Promise<{ root: Root; container: HTMLDivElement }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => { root.render(element); });
  return { root, container };
}

afterEach(() => {
  clearSession();
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("frontend authentication session", () => {
  it("keeps the access token in memory and never writes browser storage", () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    const session = vi.spyOn(Storage.prototype, "setItem");
    setAuthenticatedSession("signed-token", principal);
    expect(getSessionSnapshot().accessToken).toBe("signed-token");
    expect(local).not.toHaveBeenCalled();
    expect(session).not.toHaveBeenCalled();
  });

  it("adds the bearer token and expires the session after a 401", async () => {
    const onUnauthorized = vi.fn();
    const fetchImpl = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "AUTHENTICATION_REQUIRED", message: "expired" }),
      { status: 401 },
    ));
    const client = createApiClient({
      baseUrl: "http://api.test",
      fetchImpl,
      getAccessToken: () => "signed-token",
      onUnauthorized,
    });

    await expect(client.request("/api/v1/auth/me")).rejects.toMatchObject({ status: 401 });
    expect(new Headers(fetchImpl.mock.calls[0][1].headers).get("Authorization")).toBe("Bearer signed-token");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not render the removed manual development-token login", async () => {
    const { root, container } = await render(<AuthSessionBanner
      mode="api"
      authenticationMode="development_jwt"
      status="anonymous"
      principal={null}
      error={null}
      onLogout={vi.fn()}
    />);
    expect(container.textContent).toContain("请选择演示员工");
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent).not.toContain("验证令牌");
    await act(async () => { root.unmount(); });
  });

  it("loads demo employees without automatically issuing an admin session", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      employee_id: "CF-DEMO-001",
      display_name: "张调度",
      role: "DISPATCHER",
    }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchImpl);

    function EmployeeProbe() {
      const auth = useAuth();
      return <p>{auth.demoEmployees.map((employee) => employee.display_name).join(" / ")}</p>;
    }

    const { root, container } = await render(<AuthProvider><EmployeeProbe /></AuthProvider>);
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/api/v1/auth/demo-employees",
      expect.objectContaining({ method: "GET" }),
    );
    expect(fetchImpl).toHaveBeenCalledOnce();
    expect(getSessionSnapshot().accessToken).toBeNull();
    expect(container.textContent).toContain("张调度");
    await act(async () => { root.unmount(); });
  });

  it("posts only the selected employee id and keeps the returned token in memory", async () => {
    const fetchImpl = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/demo-employees")) {
        return new Response(JSON.stringify([{
          employee_id: "CF-DEMO-001",
          display_name: "张调度",
          role: "DISPATCHER",
        }]), { status: 200 });
      }
      return new Response(JSON.stringify({
        access_token: "employee-session-token",
        token_type: "bearer",
        expires_in: 600,
        principal: { ...principal, subject_id: "CF-DEMO-001", display_name: "张调度", roles: ["DISPATCHER"] },
      }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchImpl);

    function EmployeeProbe() {
      const auth = useAuth();
      return <button type="button" onClick={() => void auth.switchDemoEmployee("CF-DEMO-001")}>选择张调度</button>;
    }

    const { root, container } = await render(<AuthProvider><EmployeeProbe /></AuthProvider>);
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 0)); });
    await act(async () => { container.querySelector("button")?.click(); });

    const [, options] = fetchImpl.mock.calls.at(-1) ?? [];
    expect(JSON.parse(String(options?.body))).toEqual({ employee_id: "CF-DEMO-001" });
    expect(getSessionSnapshot().accessToken).toBe("employee-session-token");
    expect(getSessionSnapshot().principal?.roles).toEqual(["DISPATCHER"]);
    await act(async () => { root.unmount(); });
  });

  it("distinguishes unauthenticated and forbidden permission states", async () => {
    const anonymous = await render(<PermissionGate mode="api" status="expired" permissions={[]} required="monitor:read"><p>secret</p></PermissionGate>);
    expect(anonymous.container.textContent).toContain("会话已过期");
    expect(anonymous.container.textContent).not.toContain("secret");
    await act(async () => { anonymous.root.unmount(); });

    const denied = await render(<PermissionGate mode="api" status="authenticated" permissions={["runtime:read"]} required="monitor:read"><p>secret</p></PermissionGate>);
    expect(denied.container.textContent).toContain("无权访问");
    expect(denied.container.textContent).not.toContain("secret");
    await act(async () => { denied.root.unmount(); });
  });

  it("keeps the five approved role action guards aligned with the backend contract", () => {
    const dispatcher = permissionsForRole("DISPATCHER");
    const supervisor = permissionsForRole("SUPERVISOR");
    const operator = permissionsForRole("OPERATOR");
    const auditor = permissionsForRole("AUDITOR");
    const admin = permissionsForRole("ADMIN");

    expect(dispatcher).toContain(PERMISSIONS.DISPATCH_CREATE);
    expect(dispatcher).not.toContain(PERMISSIONS.RUNTIME_OVERRIDE);
    expect(supervisor).toContain(PERMISSIONS.RUNTIME_OVERRIDE);
    expect(operator).toContain(PERMISSIONS.MONITOR_READ);
    expect(operator).not.toContain(PERMISSIONS.MEMORY_MUTATE);
    expect(auditor).toContain(PERMISSIONS.AUDIT_READ);
    expect(auditor).not.toContain(PERMISSIONS.DISPATCH_CREATE);
    expect(admin).toEqual(expect.arrayContaining(Object.values(PERMISSIONS)));
  });
});
