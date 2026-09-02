import { primaryRole } from "../auth/principal-view";
import type { Permission, Role } from "../auth/permissions";
import type { NavigationGroup, NavigationGroupId } from "./navigation-model";
import { NAVIGATION_REGISTRY } from "./navigation-registry";

const GROUPS: readonly { id: NavigationGroupId; label: string }[] = [
  { id: "home", label: "首页" },
  { id: "business", label: "业务" },
  { id: "ai", label: "AI 与记忆" },
  { id: "runtime", label: "运行治理" },
  { id: "operations", label: "可观测性" },
  { id: "governance", label: "治理" },
];

export interface NavigationPrincipal {
  roles: readonly Role[];
  permissions: readonly Permission[];
}

export function resolveNavigation({ roles, permissions }: NavigationPrincipal): NavigationGroup[] {
  const permissionSet = new Set<Permission>(permissions);
  const selectedRole = primaryRole(roles);
  const items = NAVIGATION_REGISTRY.filter((item) => {
    if (!item.requiredPermissions.every((permission) => permissionSet.has(permission))) return false;
    if (item.landingRole) return item.landingRole === selectedRole;
    if (item.presentationRoles) return selectedRole !== null && item.presentationRoles.includes(selectedRole);
    return true;
  });

  return GROUPS.map((group) => ({
    ...group,
    items: items.filter((item) => item.group === group.id),
  })).filter((group) => group.items.length > 0);
}

export function flattenNavigationLabels(groups: readonly NavigationGroup[]): string[] {
  return groups.flatMap((group) => group.items.map((item) => item.label));
}
