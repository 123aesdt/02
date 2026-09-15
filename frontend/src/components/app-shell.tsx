import {
  Bell,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Radar,
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
import { LoginPage } from "../pages/login/login-page";
import { NavigationNotice } from "./navigation-notice";
import { RoleNavigation } from "./role-navigation";

type PagePresentation = {
  title: string;
  subtitle: string;
  tags: readonly string[];
  motto: string;
};

const pagePresentations: Record<string, PagePresentation> = {
  "/": { title: "运营总览", subtitle: "掌握县域物流全局运行态势，让每一次配送更高效、更可靠。", tags: ["全域协同", "实时洞察", "智能预警"], motto: "数智赋能县域 · 物流连接民生" },
  "/anomalies": { title: "异常中心", subtitle: "统一识别、研判和处置运输异常，确保风险有迹可循。", tags: ["实时识别", "分级处置", "闭环追踪"], motto: "更早发现 · 更快处置" },
  "/orders": { title: "运单管理", subtitle: "统一运单跟踪与全生命周期管理，让每一单物流可视、可控、可追溯。", tags: ["全程追踪", "状态可视", "责任可溯"], motto: "每一单都在路上 · 每一程都有温度" },
  "/agents": { title: "智能体中心", subtitle: "多智能体协同，打造县域物流智能大脑。", tags: ["专业智能体", "协同规划", "工具调用", "持续进化"], motto: "多智能体协同 · 让县域物流更智能" },
  "/memory": { title: "记忆中心", subtitle: "沉淀运营记忆，构建向量知识并关联业务事实，让经验持续增长。", tags: ["知识沉淀", "关系检索", "业务复用"], motto: "让每一次运营 · 都成为可沉淀的智慧" },
  "/monitor": { title: "系统监控", subtitle: "全链路监控、告警预警、日志分析与链路追踪，保障系统稳定高效运行。", tags: ["实时监控", "日志", "链路", "告警"], motto: "稳定的系统 · 是更好的物流服务" },
  "/workspace": { title: "调度工作台", subtitle: "从异常研判到运力接管，在一个工作台完成闭环调度。", tags: ["异常研判", "运力编排", "处置闭环"], motto: "让调度更有依据" },
  "/supervisor": { title: "调度主管台", subtitle: "掌握重点任务、资源冲突和处置进展，保障县域运力有序流动。", tags: ["全局监管", "资源协调", "风险控制"], motto: "统筹全域运力 · 守护履约承诺" },
  "/operations": { title: "运行中心", subtitle: "聚合系统服务、实时任务与运营数据，快速定位运行风险。", tags: ["运行分析", "服务治理", "持续优化"], motto: "稳定运行 · 畅通县域" },
  "/audit": { title: "审计中心", subtitle: "汇聚操作证据与决策轨迹，让关键业务过程可信、可查、可复核。", tags: ["证据留痕", "决策可释", "责任可溯"], motto: "每一次决策都有依据" },
  "/overview": { title: "系统总览", subtitle: "汇聚车辆、运单、异常和服务状态，快速把握运营全貌。", tags: ["核心指标", "业务总览", "实时状态"], motto: "一屏掌握全域运营" },
  "/fleet-live-map": { title: "车辆态势地图", subtitle: "实时掌握县域物流车辆运行状态、精准定位、全程可视、智能预警。", tags: ["全域车辆", "实时位置", "线路运行", "异常预警"], motto: "车行县域 · 畅达民生" },
  "/my-tasks": { title: "我的任务", subtitle: "聚焦当前配送任务、车辆状态和异常处置进度。", tags: ["任务清晰", "路线同步", "处置透明"], motto: "每一次出发都更安心" },
  "/report-issue": { title: "提出配送问题", subtitle: "快速上报车辆与配送异常，系统将自动启动安全处置流程。", tags: ["快速上报", "安全停车", "自动调度"], motto: "及时发现 · 快速响应" },
  "/team-tasks": { title: "团队任务", subtitle: "统一查看团队任务分布和处置状态。", tags: ["团队协同", "状态共享", "任务跟踪"], motto: "协同让配送更顺畅" },
  "/reviews": { title: "待复核", subtitle: "对高风险或不确定任务进行人工复核，确保业务安全合规。", tags: ["人机协同", "风险可控", "责任可追溯"], motto: "人工把关 · 让每一单更可靠" },
  "/runtime": { title: "运行状态", subtitle: "实时掌握平台与服务组件的运行健康状况，保障系统稳定、安全运行。", tags: ["稳定运行", "高效支撑", "及时响应", "持续优化"], motto: "稳定运行 · 保障县域物流畅通" },
  "/dispatch": { title: "智能调度", subtitle: "基于实时订单、路况和车辆状态生成可解释的运力调度方案。", tags: ["全局优化", "智能匹配", "动态调整", "降本增效"], motto: "AI 让每一公里 · 更高效地抵达" },
};

const fallbackPresentation: PagePresentation = {
  title: "运营工作区",
  subtitle: "连接县域物流资源与业务流程，持续提升履约效率。",
  tags: ["实时协同", "业务可视", "智能处置"],
  motto: "连接县域 · 服务民生",
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
  const presentation = location.pathname.startsWith("/dispatch/")
    ? { ...pagePresentations["/dispatch"], title: "智能调度详情", subtitle: "查看调度方案、路线证据、智能体过程与执行结果。" }
    : pagePresentations[location.pathname] ?? fallbackPresentation;
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

  if (runtimeConfig.dataMode === "api" && auth.status !== "authenticated") {
    return <LoginPage
      employees={auth.demoEmployees}
      loading={auth.demoEmployeesLoading}
      status={auth.status}
      error={auth.error}
      onLogin={auth.switchDemoEmployee}
    />;
  }

  return <div className={`app-shell ${collapsed ? "is-collapsed" : ""}`} data-current-page={location.pathname}>
    <aside className="sidebar" data-surface="sidebar">
      <div className="brand">
        <div className="brand-mark"><Boxes size={21} /></div>
        {!collapsed ? <div><strong>CountyFlow</strong><span>县域物流运营中心</span></div> : null}
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
        <div className="topbar-slogan"><Radar size={17} /><span>数智物流 · 连接县域 · 服务民生</span></div>
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
      <section className="page-hero" data-surface="page-hero" aria-labelledby="page-hero-title">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">CountyFlow / 县域物流运营中心</p>
          <h1 id="page-hero-title">{presentation.title}</h1>
          <p className="page-hero__subtitle">{presentation.subtitle}</p>
          <div className="page-hero__tags" aria-label="页面能力">
            {presentation.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
        </div>
        <p className="page-hero__motto">{presentation.motto}</p>
      </section>
      <ConnectedAuthSessionBanner />
      <NavigationNotice />
      <div className="page-content" data-surface="content"><Outlet /></div>
    </main>
  </div>;
}
