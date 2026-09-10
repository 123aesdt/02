import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppShell } from "../components/app-shell";
import { useAuth } from "../auth/auth-state";
import { RequirePermission } from "../auth/permission-gate";
import { runtimeConfig } from "../config/runtime";
import { resolveRoleLanding } from "../navigation/role-landing-resolver";
import { AdminOverviewPage } from "../pages/admin-overview-page";
import { AuditPage } from "../pages/audit-page";
import { DispatcherWorkspacePage } from "../pages/dispatcher-workspace-page";
import { DispatchDetailPage } from "../pages/dispatch-detail-page";
import { DispatchTaskCenterPage } from "../pages/dispatch-task-center-page";
import { FleetLiveMapPage } from "../pages/fleet-live-map-page";
import { AnomaliesPage } from "../pages/anomalies-page";
import { AgentsPage } from "../pages/agents-page";
import { MemoryPage } from "../pages/memory-page";
import { MonitorPage } from "../pages/monitor-page";
import { MyTasksPage } from "../pages/my-tasks-page";
import { ReportIssuePage } from "../pages/report-issue-page";
import { NotExposedPage } from "../pages/not-exposed-page";
import { OperationsPage } from "../pages/operations-page";
import { OrdersPage } from "../pages/orders-page";
import { ReviewsPage } from "../pages/reviews-page";
import { RuntimePage } from "../pages/runtime-page";
import { SupervisorWorkspacePage } from "../pages/supervisor-workspace-page";

export function RoleLandingRedirect() {
  const auth = useAuth();
  const roles = auth.principal?.roles ?? (runtimeConfig.dataMode === "mock" ? ["ADMIN"] : []);
  const target = resolveRoleLanding(roles);

  if (auth.status === "authenticated" || runtimeConfig.dataMode === "mock") {
    return target
      ? <Navigate replace to={target} />
      : <section className="authorization-state" role="alert"><h2>未配置工作区</h2><p>当前服务端身份没有可识别的 CountyFlow 角色。</p></section>;
  }
  return <section className="authorization-state" role="alert">
    <h2>{auth.status === "expired" ? "会话已过期" : "正在确认身份"}</h2>
    <p>身份确认后将进入角色默认工作区；API 模式不会回退演示数据。</p>
  </section>;
}

export const router = createBrowserRouter([{ path: "/", element: <AppShell />, children: [
  { index: true, element: <RoleLandingRedirect /> },
  { path: "workspace", element: <RequirePermission permission="dispatch:create"><DispatcherWorkspacePage /></RequirePermission> },
  { path: "supervisor", element: <RequirePermission permission="dispatch:review"><SupervisorWorkspacePage /></RequirePermission> },
  { path: "operations", element: <RequirePermission permission="monitor:read"><OperationsPage /></RequirePermission> },
  { path: "audit", element: <RequirePermission permission="audit:read"><AuditPage /></RequirePermission> },
  { path: "overview", element: <RequirePermission permission="system:admin"><AdminOverviewPage /></RequirePermission> },
  { path: "my-tasks", element: <RequirePermission permission="dispatch:read"><MyTasksPage /></RequirePermission> },
  { path: "report-issue", element: <RequirePermission permission="anomalies:report"><ReportIssuePage /></RequirePermission> },
  { path: "team-tasks", element: <RequirePermission permission="dispatch:review"><NotExposedPage title="团队任务" message="团队任务读取接口尚未开放" /></RequirePermission> },
  { path: "reviews", element: <RequirePermission permission="dispatch:review"><ReviewsPage /></RequirePermission> },
  { path: "runtime", element: <RequirePermission permission="runtime:read"><RuntimePage /></RequirePermission> },
  { path: "dispatch", element: <RequirePermission permission="dispatch:create"><DispatchTaskCenterPage /></RequirePermission> },
  { path: "fleet-live-map", element: <RequirePermission permission="dispatch:review"><FleetLiveMapPage /></RequirePermission> },
  { path: "dispatch/:taskId", element: <RequirePermission permission="dispatch:read"><DispatchDetailPage /></RequirePermission> },
  { path: "anomalies", element: <RequirePermission permission="anomalies:read"><AnomaliesPage /></RequirePermission> },
  { path: "orders", element: <RequirePermission permission="orders:read"><OrdersPage /></RequirePermission> },
  { path: "agents", element: <RequirePermission permission="agents:read"><AgentsPage /></RequirePermission> },
  { path: "memory", element: <RequirePermission permission="memory:read"><MemoryPage /></RequirePermission> },
  { path: "monitor", element: <RequirePermission permission="monitor:read"><MonitorPage /></RequirePermission> },
] }]);
