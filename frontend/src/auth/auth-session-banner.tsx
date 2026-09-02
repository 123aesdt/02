import { runtimeConfig } from "../config/runtime";
import { useAuth } from "./auth-state";
import type { AuthStatus, Principal } from "./session";
import { localizeRole } from "./principal-view";
import type { Role } from "./permissions";

interface AuthSessionBannerProps {
  mode: "mock" | "api";
  authenticationMode: "development_jwt" | "oidc_jwt";
  status: AuthStatus;
  principal: Principal | null;
  error: string | null;
  onLogout: () => Promise<void> | void;
}

export function AuthSessionBanner(props: AuthSessionBannerProps) {
  if (props.mode !== "api") return null;
  const development = props.authenticationMode === "development_jwt";
  if (props.status === "authenticated" && props.principal) {
    return <div className="auth-session-banner authenticated"><span><b>{development ? "演示员工已接入" : props.principal.display_name}</b> · {development ? `${props.principal.display_name} · ` : ""}{props.principal.roles.map((role) => localizeRole(role as Role)).join(" / ")}</span><button type="button" onClick={() => void props.onLogout()}>退出</button></div>;
  }
  return <div className="auth-session-banner">
    <span><b>{development ? "演示员工账号" : "OIDC 认证"}</b>{development ? " · 请选择演示员工，无需密码" : props.status === "expired" ? " · 会话已过期" : " · 请通过组织身份入口重新认证"}</span>
    {props.error ? <small role="alert">{props.error}</small> : null}
  </div>;
}

export function ConnectedAuthSessionBanner() {
  const auth = useAuth();
  return <AuthSessionBanner
    mode={runtimeConfig.dataMode}
    authenticationMode={runtimeConfig.authenticationMode}
    status={auth.status}
    principal={auth.principal}
    error={auth.error}
    onLogout={auth.logout}
  />;
}
