import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { runtimeConfig } from "../config/runtime";
import { localizeRole, primaryRole } from "./principal-view";
import type { Role } from "./permissions";
import { useAuth } from "./auth-state";

const PREVIEW_ROLES: readonly Role[] = ["EMPLOYEE", "DISPATCHER", "SUPERVISOR", "OPERATOR", "AUDITOR", "ADMIN"];

export function isDevRolePreviewEnabled({ isDevelopmentBuild, dataMode, authenticationMode }: {
  isDevelopmentBuild: boolean;
  dataMode: "mock" | "api";
  authenticationMode: "development_jwt" | "oidc_jwt";
}): boolean {
  return isDevelopmentBuild && dataMode === "api" && authenticationMode === "development_jwt";
}

export function DevRolePreview({ enabled, currentRole, pending = false, onSelect }: {
  enabled: boolean;
  currentRole: Role | null;
  pending?: boolean;
  onSelect: (role: Role) => Promise<void> | void;
}) {
  if (!enabled) return null;
  return <label className="dev-role-preview">
    <span>开发角色预览</span>
    <select
      aria-label="开发角色预览"
      value={currentRole ?? "ADMIN"}
      disabled={pending}
      onChange={(event) => void onSelect(event.target.value as Role)}
    >
      {PREVIEW_ROLES.map((role) => <option key={role} value={role}>{localizeRole(role)}</option>)}
    </select>
  </label>;
}

export function ConnectedDevRolePreview() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const enabled = isDevRolePreviewEnabled({
    isDevelopmentBuild: import.meta.env.DEV,
    dataMode: runtimeConfig.dataMode,
    authenticationMode: runtimeConfig.authenticationMode,
  });

  return <DevRolePreview
    enabled={enabled && typeof auth.switchDevelopmentRole === "function"}
    currentRole={primaryRole(auth.principal?.roles ?? [])}
    pending={pending}
    onSelect={async (role) => {
      if (!auth.switchDevelopmentRole) return;
      setPending(true);
      try {
        await auth.switchDevelopmentRole(role);
        navigate("/", { replace: true });
      } finally {
        setPending(false);
      }
    }}
  />;
}
