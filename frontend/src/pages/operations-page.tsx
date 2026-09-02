import { Link } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { LiveObservabilityPanel } from "../components/live-observability-panel";
import { Metric } from "../components/workspace-ui";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { isDemoSnapshotEnabled } from "../demo/demo-snapshots";
import { useObservability } from "../hooks/use-observability";
import { useRuntimeThreadsRead } from "../hooks/use-workspace-reads";
import type { ObservabilityState, ObservabilitySummary, ObservabilityWindow } from "../types/observability";
import type { WorkspaceReadHookState } from "../hooks/use-workspace-reads";
import type { PageResponse, RuntimeThreadListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

function runtimeStatusLabel(status: string) {
  if (status === "OVERRIDING") return "干预中";
  if (status === "TERMINAL") return "已结束";
  return localizeStatus(status);
}

function RuntimeSummary({ read }: { read: WorkspaceReadHookState<PageResponse<RuntimeThreadListItem>> }) {
  if (read.state === "LOADING") return <Skeleton label="正在加载运行线程摘要" lines={3} />;
  if (read.state === "EMPTY") return <EmptyState kind="empty" title="当前没有运行线程" description="接口已连接，首个分页为空。" action={<button type="button" onClick={read.refresh}>重新读取</button>} />;
  if (read.state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看运行线程的权限" action={<button type="button" onClick={read.refresh}>重试</button>} />;
  if (read.state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="运行线程摘要暂不可用" description="可观测性面板仍保持独立来源。" action={<button type="button" onClick={read.refresh}>重试</button>} />;
  if (read.state !== "READY") return <EmptyState kind="error" title="运行线程摘要加载失败" description="未显示任何推测线程。" action={<button type="button" onClick={read.refresh}>重试</button>} />;

  const running = read.data.items.filter((item) => item.status === "RUNNING").length;
  const overriding = read.data.items.filter((item) => item.status === "OVERRIDING").length;
  return <>
    <div className="panel-heading"><span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span></div>
    <section className="metrics-grid workspace-metrics"><Metric label="运行线程" value={String(read.data.total)} note="接口返回总数" tone="teal" /><Metric label="本页运行中" value={String(running)} note="最多读取 5 条" tone="teal" /><Metric label="本页干预中" value={String(overriding)} note="最多读取 5 条" tone="amber" /></section>
    <div className="workspace-link-row">{read.data.items.map((item) => <Link key={item.row_id} to={`/dispatch/${item.task_id}`}><span>{item.thread_id}</span> <StatusBadge status={item.status} label={runtimeStatusLabel(item.status)} /></Link>)}</div>
  </>;
}

export function OperationsWorkspace({ state, data, runtime, demoFallback = false }: { state: ObservabilityState; data: ObservabilitySummary | null; runtime?: React.ReactNode; demoFallback?: boolean }) {
  const [window, setWindow] = useState<ObservabilityWindow>(data?.window ?? "5m");
  return <RoleWorkspaceFrame title="运行中心" description="查看 API、Worker、消息流、运行态与依赖健康。" actions={<Link className="button-secondary" to="/monitor">打开系统监控</Link>}>
    <section className="operations-health" aria-labelledby="operations-health-title">
      <h2 id="operations-health-title">系统健康</h2>
      <LiveObservabilityPanel state={state} data={data} window={window} onWindowChange={setWindow} demoFallback={demoFallback} />
    </section>
    <WorkspaceSection id="operations-runtime" title="运行态与智能体" description="运行态读取保持只读，列表契约缺失时明确标记。">
      <div className="workspace-link-row"><Link to="/runtime">查看运行态</Link><Link to="/agents">查看智能体</Link></div>
      {runtime ?? <EmptyState kind="not-exposed" title="全局运行线程列表接口尚未开放" description="仍可通过已知任务 ID 使用现有安全读取投影。" />}
    </WorkspaceSection>
    <WorkspaceSection id="operations-audit" title="运维审计" description="必要证据只读，不能重试或修改审计记录。">
      <div className="workspace-link-row"><Link to="/audit">打开审计中心</Link></div>
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

function ApiOperationsPage() {
  const observability = useObservability("5m");
  const runtime = useRuntimeThreadsRead({ limit: 5 });
  return <OperationsWorkspace state={observability.state} data={observability.data} runtime={<RuntimeSummary read={runtime} />} demoFallback={isDemoSnapshotEnabled(runtimeConfig)} />;
}

function MockOperationsPage() {
  return <OperationsWorkspace state="UNAVAILABLE" data={null} demoFallback />;
}

export function OperationsPage() {
  return runtimeConfig.dataMode === "api" ? <ApiOperationsPage /> : <MockOperationsPage />;
}
