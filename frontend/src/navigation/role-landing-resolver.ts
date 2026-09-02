import { primaryRole } from "../auth/principal-view";
import type { Role } from "../auth/permissions";

export type RoleLanding = "/overview" | "/supervisor" | "/operations" | "/audit" | "/workspace" | "/my-tasks";

const ROLE_LANDINGS: Record<Role, RoleLanding> = {
  EMPLOYEE: "/my-tasks",
  ADMIN: "/overview",
  SUPERVISOR: "/supervisor",
  OPERATOR: "/operations",
  AUDITOR: "/audit",
  DISPATCHER: "/workspace",
};

export function resolveRoleLanding(roles: readonly string[]): RoleLanding | null {
  const role = primaryRole(roles);
  return role ? ROLE_LANDINGS[role] : null;
}
