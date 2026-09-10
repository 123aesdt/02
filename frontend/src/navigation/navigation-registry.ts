import {
  Activity,
  Bot,
  BrainCircuit,
  ClipboardCheck,
  FileClock,
  Gauge,
  LayoutDashboard,
  ListChecks,
  MapPinned,
  MessageSquareWarning,
  PackageSearch,
  Route,
  ScrollText,
  ShieldCheck,
  TriangleAlert,
  UserRoundCheck,
} from "lucide-react";

import { PERMISSIONS } from "../auth/permissions";
import type { NavigationItem } from "./navigation-model";

export const NAVIGATION_REGISTRY: readonly NavigationItem[] = [
  { id: "dispatcher-home", label: "调度工作台", icon: LayoutDashboard, route: "/workspace", group: "home", requiredPermissions: [PERMISSIONS.DISPATCH_CREATE], visibility: "primary", landingRole: "DISPATCHER" },
  { id: "supervisor-home", label: "调度主管台", icon: ClipboardCheck, route: "/supervisor", group: "home", requiredPermissions: [PERMISSIONS.DISPATCH_REVIEW], visibility: "primary", landingRole: "SUPERVISOR" },
  { id: "operator-home", label: "运行中心", icon: Gauge, route: "/operations", group: "home", requiredPermissions: [PERMISSIONS.MONITOR_READ], visibility: "primary", landingRole: "OPERATOR" },
  { id: "auditor-home", label: "审计中心", icon: ScrollText, route: "/audit", group: "home", requiredPermissions: [PERMISSIONS.AUDIT_READ], visibility: "primary", landingRole: "AUDITOR" },
  { id: "admin-home", label: "系统总览", icon: LayoutDashboard, route: "/overview", group: "home", requiredPermissions: [PERMISSIONS.SYSTEM_ADMIN], visibility: "primary", landingRole: "ADMIN" },

  { id: "anomalies", label: "异常中心", icon: TriangleAlert, route: "/anomalies", group: "business", requiredPermissions: [PERMISSIONS.ANOMALIES_READ], visibility: "primary" },
  { id: "fleet-live-map", label: "车辆态势地图", icon: MapPinned, route: "/fleet-live-map", group: "business", requiredPermissions: [PERMISSIONS.DISPATCH_REVIEW], visibility: "contextual", presentationRoles: ["SUPERVISOR", "ADMIN"] },
  { id: "dispatch", label: "智能调度", icon: Route, route: "/dispatch", group: "business", requiredPermissions: [PERMISSIONS.DISPATCH_CREATE], visibility: "primary" },
  { id: "orders", label: "运单管理", icon: PackageSearch, route: "/orders", group: "business", requiredPermissions: [PERMISSIONS.ORDERS_READ], visibility: "primary" },
  { id: "my-tasks", label: "我的任务", icon: UserRoundCheck, route: "/my-tasks", group: "business", requiredPermissions: [PERMISSIONS.DISPATCH_READ], visibility: "contextual", presentationRoles: ["EMPLOYEE"] },
  { id: "report-issue", label: "提出问题", icon: MessageSquareWarning, route: "/report-issue", group: "business", requiredPermissions: [PERMISSIONS.ANOMALIES_REPORT], visibility: "contextual", presentationRoles: ["EMPLOYEE"] },
  { id: "team-tasks", label: "团队任务", icon: ListChecks, route: "/team-tasks", group: "business", requiredPermissions: [PERMISSIONS.DISPATCH_REVIEW], visibility: "contextual", presentationRoles: ["SUPERVISOR"] },
  { id: "reviews", label: "待复核", icon: ClipboardCheck, route: "/reviews", group: "business", requiredPermissions: [PERMISSIONS.DISPATCH_REVIEW], visibility: "contextual", presentationRoles: ["SUPERVISOR", "ADMIN"] },

  { id: "agents", label: "智能体中心", icon: Bot, route: "/agents", group: "ai", requiredPermissions: [PERMISSIONS.AGENTS_READ], visibility: "contextual", presentationRoles: ["SUPERVISOR", "OPERATOR", "ADMIN"] },
  { id: "memory", label: "记忆中心", icon: BrainCircuit, route: "/memory", group: "ai", requiredPermissions: [PERMISSIONS.MEMORY_READ], visibility: "contextual", presentationRoles: ["SUPERVISOR", "AUDITOR", "ADMIN"] },

  { id: "runtime", label: "运行态", secondaryLabel: "运行线程", icon: FileClock, route: "/runtime", group: "runtime", requiredPermissions: [PERMISSIONS.RUNTIME_READ], visibility: "contextual", presentationRoles: ["SUPERVISOR", "OPERATOR", "AUDITOR", "ADMIN"] },
  { id: "admin-operations", label: "运行中心", icon: Gauge, route: "/operations", group: "operations", requiredPermissions: [PERMISSIONS.MONITOR_READ], visibility: "contextual", presentationRoles: ["ADMIN"] },
  { id: "monitor", label: "系统监控", icon: Activity, route: "/monitor", group: "operations", requiredPermissions: [PERMISSIONS.MONITOR_READ], visibility: "primary" },

  { id: "supervisor-audit", label: "审计证据", icon: ShieldCheck, route: "/audit", group: "governance", requiredPermissions: [PERMISSIONS.AUDIT_READ], visibility: "contextual", presentationRoles: ["SUPERVISOR"] },
  { id: "operator-audit", label: "运维审计", icon: ShieldCheck, route: "/audit", group: "governance", requiredPermissions: [PERMISSIONS.AUDIT_READ], visibility: "contextual", presentationRoles: ["OPERATOR"] },
  { id: "admin-audit", label: "审计中心", icon: ShieldCheck, route: "/audit", group: "governance", requiredPermissions: [PERMISSIONS.AUDIT_READ], visibility: "contextual", presentationRoles: ["ADMIN"] },
];
