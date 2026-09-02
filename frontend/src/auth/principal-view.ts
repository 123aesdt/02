import { PERMISSIONS, type Permission, type Role } from "./permissions";
import type { Principal } from "./session";

const ROLE_PRIORITY: readonly Role[] = ["ADMIN", "SUPERVISOR", "OPERATOR", "AUDITOR", "DISPATCHER", "EMPLOYEE"];
const ROLE_LABELS: Record<Role, string> = {
  EMPLOYEE: "配送员工",
  DISPATCHER: "调度员",
  SUPERVISOR: "调度主管",
  OPERATOR: "系统运维",
  AUDITOR: "审计员",
  ADMIN: "系统管理员",
};
const ROLE_SET = new Set<string>(ROLE_PRIORITY);
const PERMISSION_SET = new Set<string>(Object.values(PERMISSIONS));

export function normalizeRoles(roles: readonly string[]): Role[] {
  return roles.filter((role): role is Role => ROLE_SET.has(role));
}

export function normalizePermissions(permissions: readonly string[]): Permission[] {
  return permissions.filter((permission): permission is Permission => PERMISSION_SET.has(permission));
}

export function primaryRole(roles: readonly string[]): Role | null {
  const values = new Set(normalizeRoles(roles));
  return ROLE_PRIORITY.find((role) => values.has(role)) ?? null;
}

export function localizeRole(role: Role): string {
  return ROLE_LABELS[role];
}

export interface PrincipalView {
  subjectId: string;
  displayName: string;
  roles: Role[];
  permissions: Permission[];
  primaryRole: Role | null;
  localizedRole: string;
}

export function adaptPrincipal(principal: Principal | null): PrincipalView | null {
  if (!principal) return null;
  const roles = normalizeRoles(principal.roles);
  const selectedRole = primaryRole(roles);
  return {
    subjectId: principal.subject_id,
    displayName: principal.display_name,
    roles,
    permissions: normalizePermissions(principal.permissions),
    primaryRole: selectedRole,
    localizedRole: selectedRole ? localizeRole(selectedRole) : "未识别角色",
  };
}
