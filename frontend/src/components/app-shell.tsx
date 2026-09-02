import {
  Bell,
  ChevronLeft,
  ChevronRight,
  Menu,
} from "lucide-react";
import { useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { ConnectedAuthSessionBanner } from "../auth/auth-session-banner";
import { ConnectedDemoEmployeeSwitcher } from "../auth/demo-employee-switcher";
import { useAuth } from "../auth/auth-state";
import { adaptPrincipal } from "../auth/principal-view";
import { runtimeConfig } from "../config/runtime";
import { useBackendHealth } from "../hooks/use-backend-health";
import { resolveNavigation } from "../navigation/navigation-resolver";
import { RoleNavigation } from "./role-navigation";

const pageTitles: Record<string, string> = {
  "/": "运营总览",
  "/anomalies": "异常中心",
  "/orders": "运单管理",
  "/agents": "智能体中心",
  "/memory": "记忆中心",
  "/monitor": "系统监控",
  "/workspace": "调度工作台",
  "/supervisor": "调度主管台",
  "/operations": "运行中心",
  "/audit": "审计中心",
  "/overview": "系统总览",
  "/my-tasks": "我的任务",
  "/report-issue": "提出配送问题",
  "/team-tasks": "团队任务",
  "/reviews": "待复核",
  "/runtime": "运行态",
};

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const auth = useAuth();
  const principal = adaptPrincipal(auth.principal);
  const navigation = principal
    ? resolveNavigation({ roles: principal.roles, permissions: principal.permissions })
    : [];
  const backendConnected = useBackendHealth();
  const title = location.pathname === "/dispatch"
    ? "智能调度"
    : location.pathname.startsWith("/dispatch")
      ? "智能调度详情"
      : pageTitles[location.pathname] ?? "运营工作区";
  const connectionLabel = runtimeConfig.dataMode === "mock"
    ? "演示数据"
    : backendConnected
      ? "后端已连接"
      : "后端状态待确认";
  const connectionDetail = runtimeConfig.dataMode === "mock"
    ? "非生产数据"
    : backendConnected
      ? "实时 API"
      : "请检查本地服务";

  return <div className={`app-shell ${collapsed ? "is-collapsed" : ""}`}>
    <aside className="sidebar" data-surface="sidebar">
      <div className="brand">
        <div className="brand-mark"><Menu size={18} /></div>
        {!collapsed ? <div><strong>CountyFlow</strong><span>AI 智能调度</span></div> : null}
      </div>
      <RoleNavigation groups={navigation} collapsed={collapsed} />
      <div className="sidebar-footer">
        <div className="system-status">
          <span className="online-dot" data-connected={backendConnected || undefined} />
          {!collapsed ? <div><strong>{connectionLabel}</strong><small>{connectionDetail}</small></div> : null}
        </div>
        {!collapsed ? <div className="release"><span>v0.1.0</span><b>{runtimeConfig.dataMode === "api" ? "本地 API" : "演示模式"}</b></div> : null}
        <button
          className="collapse-button"
          type="button"
          aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
          aria-expanded={!collapsed}
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar" data-surface="topbar">
        <div>
          <p className="topbar-path">CountyFlow / 运营中心</p>
          <h1>{title}</h1>
        </div>
        <div className="topbar-actions">
          <span className="online-status"><i />{connectionLabel}</span>
          <span className="demo-badge">{runtimeConfig.dataMode === "api" ? "API" : "演示"}</span>
          <button className="icon-button" type="button" aria-label="通知"><Bell size={18} /></button>
          <ConnectedDemoEmployeeSwitcher />
          {principal ? <div className="principal-identity">
            <span className="principal-avatar" aria-hidden="true">{principal.displayName.slice(0, 1)}</span>
            <span><strong>{principal.displayName}</strong><small>{principal.localizedRole}</small></span>
          </div> : null}
        </div>
      </header>
      <ConnectedAuthSessionBanner />
      <div className="page-content" data-surface="content"><Outlet /></div>
    </main>
  </div>;
}
