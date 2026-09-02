import type { LucideIcon } from "lucide-react";

import type { Permission, Role } from "../auth/permissions";

export type NavigationGroupId = "home" | "business" | "ai" | "runtime" | "operations" | "governance";

export interface NavigationItem {
  id: string;
  label: string;
  secondaryLabel?: string;
  icon: LucideIcon;
  route: string;
  group: NavigationGroupId;
  requiredPermissions: readonly Permission[];
  visibility: "primary" | "contextual";
  landingRole?: Role;
  presentationRoles?: readonly Role[];
}

export interface NavigationGroup {
  id: NavigationGroupId;
  label: string;
  items: NavigationItem[];
}
