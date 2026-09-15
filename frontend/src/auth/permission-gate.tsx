import { Navigate } from "react-router-dom";

import { runtimeConfig } from "../config/runtime";
import { useAuth } from "./auth-state";
import type { AuthStatus } from "./session";

export function PermissionGate({ mode, status, permissions, required, redirectTo, redirectNotice, children }: {
  mode: "mock" | "api";
  status: AuthStatus;
  permissions: string[];
  required: string;
  redirectTo?: string;
  redirectNotice?: { title: string; detail: string };
  children: React.ReactNode;
}) {
  if (mode === "mock") return children;
  if (status !== "authenticated") {
    return <section className="authorization-state" role="alert"><h2>{status === "expired" ? "会话已过期" : "需要登录"}</h2><p>请在页面顶部完成认证后继续。API 模式不会回退演示数据。</p></section>;
  }
  if (!permissions.includes(required)) {
    return redirectTo ? <Navigate replace to={redirectTo} state={redirectNotice ? { navigationNotice: redirectNotice } : null} /> : <section className="authorization-state" role="alert"><h2>无权访问</h2><p>当前身份缺少 <code>{required}</code> 权限。</p></section>;
  }
  return children;
}

export function RequirePermission({ permission, redirectTo, redirectNotice, children }: { permission: string; redirectTo?: string; redirectNotice?: { title: string; detail: string }; children: React.ReactNode }) {
  const auth = useAuth();
  return <PermissionGate mode={runtimeConfig.dataMode} status={auth.status} permissions={auth.permissions} required={permission} redirectTo={redirectTo} redirectNotice={redirectNotice}>{children}</PermissionGate>;
}
