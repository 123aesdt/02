import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { OperationalSummary } from "../components/workspace/operational-summary";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { useReviewsRead, useRuntimeThreadsRead } from "../hooks/use-workspace-reads";
import type { ReviewListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import type { WorkspaceMetric } from "../types/workspace";
import { localizeStatus } from "../utils/presentation-labels";

const mockMetrics: WorkspaceMetric[] = [
  { id: "risk", label: "今日高风险", value: null, provenance: "NOT_EXPOSED" },
  { id: "reviews", label: "待复核", value: null, provenance: "NOT_EXPOSED" },
  { id: "interventions", label: "需要干预", value: null, provenance: "NOT_EXPOSED" },
  { id: "overrides", label: "干预次数", value: null, provenance: "NOT_EXPOSED" },
  { id: "success", label: "调度成功率", value: null, provenance: "NOT_EXPOSED" },
];

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

const reviewColumns: DataTableColumn<ReviewListItem>[] = [
  { key: "task_id", label: "任务", render: (item) => <Link to={`/dispatch/${item.task_id}`}>{item.task_id}</Link> },
  { key: "order_no", label: "运单" },
  { key: "risk", label: "风险", render: (item) => localizeStatus(item.risk) },
  { key: "reason", label: "原因" },
  { key: "vehicle_id", label: "车辆" },
  { key: "original_route_id", label: "原路线" },
  { key: "suggested_route_id", label: "建议路线" },
  { key: "status", label: "状态", render: (item) => <StatusBadge status={item.status} label={item.status === "REVIEW_REQUIRED" ? "等待人工复核" : localizeStatus(item.status)} /> },
  { key: "created_at", label: "进入复核时间" },
];

function SupervisorReviewFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载主管复核队列" lines={4} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title="当前没有等待人工复核任务" description="接口已连接，主管队列为空。" action={<button type="button" onClick={onRetry}>重新读取</button>} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看人工复核队列的权限" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="人工复核队列暂不可用" description="不会回退演示数据。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="人工复核队列加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function SupervisorRuntimeFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在读取运行态摘要" lines={3} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title="当前没有运行态摘要" description="接口已连接，首个分页为空。" action={<button type="button" onClick={onRetry}>重新读取</button>} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看运行态摘要的权限" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="运行态摘要服务暂不可用" description="不会显示推测状态。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="运行态摘要加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function MockSupervisorWorkspacePage() {
  return <RoleWorkspaceFrame title="调度主管台" description="聚焦业务风险、人工复核与稳定边界干预。">
    <OperationalSummary title="风险概览" metrics={mockMetrics} />
    <WorkspaceSection id="supervisor-reviews" title="待人工复核" description="复核动作必须由服务端契约与权限共同授权。">
      <EmptyState kind="not-exposed" title="复核队列接口尚未开放" description="演示模式不会使用静态复核任务。" />
    </WorkspaceSection>
    <WorkspaceSection id="supervisor-interventions" title="需要干预" description="强干预只在已知任务、稳定边界与服务端资格同时满足时开放。">
      <EmptyState kind="not-exposed" title="全局干预任务列表接口尚未开放" description="请从有权限的真实调度详情读取运行态干预资格后进入危险操作区。" />
    </WorkspaceSection>
    <WorkspaceSection id="supervisor-history" title="干预历史" description="历史记录必须来自现有运行态干预投影。">
      <EmptyState kind="not-exposed" title="全局干预历史接口尚未开放" description="任务级历史仍在真实运行线程详情中保留。" />
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

function ApiSupervisorWorkspacePage() {
  const reviews = useReviewsRead({ limit: 5 });
  const runtime = useRuntimeThreadsRead({ limit: 20 });
  const runtimeItems = runtime.state === "READY" ? runtime.data.items : [];
  const reviewProvenance = reviews.state === "READY" ? reviews.data.provenance : "NOT_EXPOSED";
  const runtimeProvenance = runtime.state === "READY" ? runtime.data.provenance : "NOT_EXPOSED";
  const metrics: WorkspaceMetric[] = [
    { id: "risk", label: "本页高风险", value: reviews.state === "READY" ? String(reviews.data.items.filter((item) => item.risk === "HIGH").length) : null, provenance: reviewProvenance },
    { id: "reviews", label: "待复核", value: reviews.state === "READY" ? String(reviews.data.total) : null, provenance: reviewProvenance },
    { id: "running", label: "本页运行中", value: runtime.state === "READY" ? String(runtimeItems.filter((item) => item.status === "RUNNING").length) : null, provenance: runtimeProvenance },
    { id: "stable", label: "本页稳定", value: runtime.state === "READY" ? String(runtimeItems.filter((item) => item.status === "STABLE").length) : null, provenance: runtimeProvenance },
    { id: "overriding", label: "本页干预中", value: runtime.state === "READY" ? String(runtimeItems.filter((item) => item.status === "OVERRIDING").length) : null, provenance: runtimeProvenance },
    { id: "terminal", label: "本页已结束", value: runtime.state === "READY" ? String(runtimeItems.filter((item) => item.status === "TERMINAL").length) : null, provenance: runtimeProvenance },
  ];

  return <RoleWorkspaceFrame title="调度主管台" description="聚焦业务风险、人工复核与稳定边界干预。">
    <OperationalSummary title="风险概览" metrics={metrics} />
    <WorkspaceSection id="supervisor-reviews" title="待人工复核" description="此处为只读摘要；请进入待复核页面执行批准或拒绝。" actions={<Link to="/reviews">进入复核处理</Link>}>
      {reviews.state === "READY" ? <>
        <span className={`source-label ${reviews.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(reviews.data.provenance)}</span>
        <DataTable caption="主管待人工复核队列" columns={reviewColumns} rows={reviews.data.items} rowKey={(item) => String(item.row_id)} />
      </> : <SupervisorReviewFeedback state={reviews.state} onRetry={reviews.refresh} />}
    </WorkspaceSection>
    <WorkspaceSection id="supervisor-interventions" title="运行态摘要" description="线程状态计数来自运行态第一页；强干预仍只在已知任务详情开放。" actions={<Link to="/runtime">查看运行态</Link>}>
      {runtime.state === "READY"
        ? <p><span className={`source-label ${runtime.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(runtime.data.provenance)}</span> 本页 {runtime.data.items.length} 条，接口总数 {runtime.data.total}。</p>
        : <SupervisorRuntimeFeedback state={runtime.state} onRetry={runtime.refresh} />}
    </WorkspaceSection>
    <WorkspaceSection id="supervisor-history" title="干预历史" description="历史记录必须来自现有运行态干预投影。">
      <EmptyState kind="not-exposed" title="全局干预历史接口尚未开放" description="任务级干预历史仍在真实运行线程详情中保留。" />
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

export function SupervisorWorkspacePage() {
  return runtimeConfig.dataMode === "api" ? <ApiSupervisorWorkspacePage /> : <MockSupervisorWorkspacePage />;
}
