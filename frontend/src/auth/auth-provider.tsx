import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { runtimeConfig } from "../config/runtime";
import { createApiClient } from "../services/api/client";
import { AuthContext, type AuthContextValue } from "./auth-state";
import type { DemoEmployee, DemoEmployeeSessionResponse } from "./demo-employees";
import type { Role } from "./permissions";
import {
  clearSession,
  expireSession,
  getSessionSnapshot,
  setAuthenticatedSession,
  setAuthenticating,
  subscribeToSession,
} from "./session";

const demoEmployeeMode = runtimeConfig.dataMode === "api"
  && runtimeConfig.authenticationMode === "development_jwt";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const session = useSyncExternalStore(subscribeToSession, getSessionSnapshot, getSessionSnapshot);
  const [error, setError] = useState<string | null>(null);
  const [demoEmployees, setDemoEmployees] = useState<readonly DemoEmployee[]>([]);
  const [demoEmployeesLoading, setDemoEmployeesLoading] = useState(demoEmployeeMode);

  const startDevelopmentSession = useCallback(async (role: Role = "ADMIN") => {
    setError(null);
    setAuthenticating();
    const client = createApiClient({
      baseUrl: runtimeConfig.apiBaseUrl,
      getAccessToken: () => null,
      onUnauthorized: () => undefined,
    });
    try {
      const response = await client.request<DemoEmployeeSessionResponse>(
        "/api/v1/auth/development-session",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role }),
        },
      );
      setAuthenticatedSession(response.data.access_token, response.data.principal);
    } catch {
      clearSession();
      setError("开发身份自动接入失败，请确认本地后端已启动。");
    }
  }, []);

  const switchDemoEmployee = useCallback(async (employeeId: string) => {
    setError(null);
    setAuthenticating();
    const client = createApiClient({
      baseUrl: runtimeConfig.apiBaseUrl,
      getAccessToken: () => null,
      onUnauthorized: () => undefined,
    });
    try {
      const response = await client.request<DemoEmployeeSessionResponse>(
        "/api/v1/auth/demo-session",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ employee_id: employeeId }),
        },
      );
      setAuthenticatedSession(response.data.access_token, response.data.principal);
    } catch {
      clearSession();
      setError("演示员工身份接入失败，请确认账号仍处于启用状态。");
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      if (session.accessToken) {
        const client = createApiClient({ baseUrl: runtimeConfig.apiBaseUrl });
        await client.request("/api/v1/auth/logout", { method: "POST" });
      }
    } finally {
      clearSession();
    }
  }, [session.accessToken]);

  useEffect(() => {
    if (!demoEmployeeMode) return undefined;
    let active = true;
    const client = createApiClient({
      baseUrl: runtimeConfig.apiBaseUrl,
      getAccessToken: () => null,
      onUnauthorized: () => undefined,
    });
    void client.request<DemoEmployee[]>("/api/v1/auth/demo-employees", { method: "GET" })
      .then((response) => {
        if (!active) return;
        setDemoEmployees(response.data);
        setDemoEmployeesLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setDemoEmployees([]);
        setDemoEmployeesLoading(false);
        setError("演示员工账号加载失败，请确认本地后端和数据库已启动。");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (session.status !== "authenticated" || !session.principal) return undefined;
    const remaining = Date.parse(session.principal.expires_at) - Date.now();
    if (remaining <= 0) {
      expireSession();
      return undefined;
    }
    const timer = window.setTimeout(expireSession, remaining);
    return () => window.clearTimeout(timer);
  }, [session.principal, session.status]);

  const value = useMemo<AuthContextValue>(() => ({
    status: session.status,
    principal: session.principal,
    permissions: session.principal?.permissions ?? [],
    error,
    demoEmployees,
    demoEmployeesLoading,
    logout,
    switchDemoEmployee,
    switchDevelopmentRole: startDevelopmentSession,
  }), [
    demoEmployees,
    demoEmployeesLoading,
    error,
    logout,
    session.principal,
    session.status,
    startDevelopmentSession,
    switchDemoEmployee,
  ]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
