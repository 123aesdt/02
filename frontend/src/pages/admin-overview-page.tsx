import { Link } from "react-router-dom";

import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { Metric } from "../components/workspace-ui";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { demoCapabilitySummaries, isDemoSnapshotEnabled } from "../demo/demo-snapshots";
import { useOverview } from "../hooks/use-workspace-reads";
import type { WorkspaceReadProvenance } from "../types/workspace-read-models";

const capabilities = [
  { title: "业务健康", route: "/anomalies", detail: "异常与调度业务入口；统一健康汇总未开放。", hasOverviewSource: true },
  { title: "智能体", route: "/agents", detail: "智能体运行状态与能力入口。", hasOverviewSource: false },
  { title: "记忆", route: "/memory", detail: "实体关系、向量记忆与共享控制入口。", hasOverviewSource: false },
  { title: "运行", route: "/runtime", detail: "线程、Checkpoint 与任务级治理入口。", hasOverviewSource: true },
  { title: "可观测性", route: "/monitor", detail: "真实监控摘要、依赖与趋势入口。", hasOverviewSource: false },
  { title: "治理与安全", route: "/audit", detail: "只读安全审计与任务级证据入口。", hasOverviewSource: false },
] as const;

function provenanceLabel(provenance: WorkspaceReadProvenance) { return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据"; }

function OverviewReadFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载系统总览" lines={4} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看系统总览的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="服务暂不可用" description="请稍后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="系统总览加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

export function AdminOverviewPage() {
  const read = useOverview();
  if (runtimeConfig.dataMode === "api") {
    if (read.state !== "READY") return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。"><WorkspaceSection id="admin-summary" title="产品能力总览" description="正在读取已开放的领域计数。"><OverviewReadFeedback state={read.state} onRetry={read.refresh} /></WorkspaceSection></RoleWorkspaceFrame>;
    const source = provenanceLabel(read.data.provenance);
    const demoEnabled = isDemoSnapshotEnabled(runtimeConfig);
    const sectionDescription = demoEnabled ? "实时计数与演示摘要；虚拟内容均已单独标识。" : "仅展示接口已返回的领域计数。";
    return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。"><WorkspaceSection id="admin-summary" title="产品能力总览" description={sectionDescription}><section className="metrics-grid workspace-metrics"><Metric label="运单" value={String(read.data.orders)} note="接口返回计数"/><Metric label="异常" value={String(read.data.anomalies)} note="接口返回计数" tone="amber"/><Metric label="待复核" value={String(read.data.reviews)} note="接口返回计数" tone="violet"/><Metric label="运行线程" value={String(read.data.runtime_threads)} note="接口返回计数" tone="teal"/></section><div className="admin-capability-grid">{capabilities.map((capability) => {
      const demoSummary = demoCapabilitySummaries[capability.title as keyof typeof demoCapabilitySummaries];
      const showDemoSummary = demoEnabled && !capability.hasOverviewSource && Boolean(demoSummary);
      return <article className="admin-capability-card" key={capability.route}><div><Link to={capability.route}>{capability.title}</Link><p>{showDemoSummary ? demoSummary : capability.hasOverviewSource ? "接口领域计数已接入。" : capability.detail}</p></div>{capability.hasOverviewSource ? <StatusBadge status={read.data.provenance} label={source} /> : showDemoSummary ? <StatusBadge status="DEMO" label="演示数据" /> : <StatusBadge status="NOT_EXPOSED" label="待独立数据源" />}</article>;
    })}</div></WorkspaceSection></RoleWorkspaceFrame>;
  }
  return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。"><WorkspaceSection id="admin-summary" title="产品能力总览" description="仅连接已存在的专业页面；跨域汇总值未开放。"><div className="admin-capability-grid">{capabilities.map((capability) => <article className="admin-capability-card" key={capability.route}><div><Link to={capability.route}>{capability.title}</Link><p>{capability.detail}</p></div><StatusBadge status="NOT_EXPOSED" label="汇总未开放" /></article>)}</div></WorkspaceSection></RoleWorkspaceFrame>;
}
