import { Link } from "react-router-dom";

import { useHasPermission } from "../auth/auth-state";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { OperationalSummary } from "../components/workspace/operational-summary";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { TaskQueue } from "../components/workspace/task-queue";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { useMyTasksRead } from "../hooks/use-workspace-reads";
import type { WorkspaceMetric, WorkspaceTask } from "../types/workspace";
import type { MyTaskListItem } from "../types/workspace-read-models";

function toWorkspaceTasks(items: readonly MyTaskListItem[]): WorkspaceTask[] {
  return items.map((item) => ({
    taskId: item.task_id,
    title: item.description ?? item.order_no ?? "调度任务",
    status: item.status,
    risk: item.risk ?? "—",
    waitingSince: item.updated_at,
    detailHref: `/dispatch/${item.task_id}`,
  }));
}

function TaskReadFeedback({ state, onRetry, loadingLabel, emptyTitle }: { state: string; onRetry: () => void; loadingLabel: string; emptyTitle: string }) {
  if (state === "LOADING") return <Skeleton label={loadingLabel} lines={4} />;
  if (state === "EMPTY") return <TaskQueue tasks={[]} emptyTitle={emptyTitle} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看我的任务的权限" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="我的任务服务暂不可用" description="不会回退静态任务。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "NOT_EXPOSED") return <EmptyState kind="not-exposed" title="我的任务未开放" />;
  return <EmptyState kind="error" title="我的任务加载失败" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

function TaskProjection({ read, loadingLabel, emptyTitle }: { read: ReturnType<typeof useMyTasksRead>; loadingLabel: string; emptyTitle: string }) {
  if (read.state === "READY" && read.data) {
    return <TaskQueue tasks={toWorkspaceTasks(read.data.items)} emptyTitle={emptyTitle} />;
  }
  return <TaskReadFeedback state={read.state} onRetry={read.refresh} loadingLabel={loadingLabel} emptyTitle={emptyTitle} />;
}

export function DispatcherWorkspacePage() {
  const canCreate = useHasPermission("dispatch:create");
  const readyRead = useMyTasksRead({ limit: 5, state: "READY" });
  const activeRead = useMyTasksRead({ limit: 5, state: "ACTIVE" });
  const endedRead = useMyTasksRead({ limit: 5, state: "ENDED" });
  const summarySource = readyRead.data ?? activeRead.data ?? endedRead.data;
  const summary = summarySource?.summary;
  const metrics: WorkspaceMetric[] = [
    { id: "total", label: "全部任务", value: summary ? String(summary.total) : null, provenance: summarySource?.provenance ?? "NOT_EXPOSED" },
    { id: "ready", label: "待执行", value: summary ? String(summary.ready) : null, provenance: summarySource?.provenance ?? "NOT_EXPOSED" },
    { id: "waiting", label: "等待中", value: summary ? String(summary.waiting) : null, provenance: summarySource?.provenance ?? "NOT_EXPOSED" },
    { id: "active", label: "处理中", value: summary ? String(summary.active) : null, provenance: summarySource?.provenance ?? "NOT_EXPOSED" },
    { id: "ended", label: "已结束", value: summary ? String(summary.ended) : null, provenance: summarySource?.provenance ?? "NOT_EXPOSED" },
  ];
  return <RoleWorkspaceFrame
    title="调度工作台"
    description="聚焦需要处理的异常、调度任务与业务证据。"
    actions={canCreate ? <Link className="button-primary" to="/dispatch">发起智能调度</Link> : null}
  >
    <OperationalSummary title="工作概览" metrics={metrics} />
    <WorkspaceSection id="dispatcher-tasks" title="待执行任务" description="仅展示服务端确认归属当前员工且可进入执行的任务。">
      <TaskProjection read={readyRead} loadingLabel="正在加载待执行任务" emptyTitle="当前没有待执行任务" />
    </WorkspaceSection>
    <WorkspaceSection id="dispatcher-running" title="调度执行中" description="异步任务必须来自真实任务状态与事件流。">
      <TaskProjection read={activeRead} loadingLabel="正在加载执行中任务" emptyTitle="当前没有执行中的任务" />
    </WorkspaceSection>
    <WorkspaceSection id="dispatcher-recommendations" title="AI 建议" description="建议必须保留来源、原因与降级证据。">
      <EmptyState kind="not-exposed" title="工作区级 AI 建议接口尚未开放" description="不会在 API 模式下展示静态推荐。" />
    </WorkspaceSection>
    <WorkspaceSection id="dispatcher-completed" title="最近完成" description="仅展示服务端确认的终态任务。">
      <TaskProjection read={endedRead} loadingLabel="正在加载最近完成任务" emptyTitle="当前没有已完成任务" />
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
