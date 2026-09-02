import { createContext, useContext, useSyncExternalStore } from "react";

import { runtimeConfig } from "../config/runtime";
import { getSessionSnapshot, subscribeToSession, type AuthStatus, type Principal } from "./session";
import type { Role } from "./permissions";
import type { DemoEmployee } from "./demo-employees";

export interface AuthContextValue {
  status: AuthStatus;
  principal: Principal | null;
  permissions: string[];
  error: string | null;
  demoEmployees: readonly DemoEmployee[];
  demoEmployeesLoading: boolean;
  logout: () => Promise<void>;
  switchDemoEmployee: (employeeId: string) => Promise<void>;
  switchDevelopmentRole?: (role: Role) => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}

export function useHasPermission(permission: string): boolean {
  const session = useSyncExternalStore(subscribeToSession, getSessionSnapshot, getSessionSnapshot);
  return runtimeConfig.dataMode === "mock" || session.principal?.permissions.includes(permission) === true;
}
