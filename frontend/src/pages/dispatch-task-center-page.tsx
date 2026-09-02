import { Link } from "react-router-dom";

import { useAuth } from "../auth/auth-state";
import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { useAnomaliesRead } from "../hooks/use-workspace-reads";
import type { AnomalyListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

const columns: DataTableColumn<AnomalyListItem>[] = [
  { key: "anomaly_no", label: "异常编号" },
  { key: "order_no", label: "运单" },
  { key: "anomaly_type", label: "问题类型" },
  { key: "risk", label: "风险", render: (item) => localizeStatus(item.risk) },
  { key: "description", label: "问题描述" },
  { key: "driver_id", label: "司机" },
  { key: "vehicle_id", label: "车辆" },
  { key: "status", label: "异常状态", render: (item) => <StatusBadge status={item.status} label={localizeStatus(item.status)} /> },
  { key: "latest_task_id", label: "AI 调度任务", render: (item) => item.latest_task_id
    ? <Link className="inline-link" to={`/dispatch/${item.latest_task_id}`}>{item.latest_task_id}</Link>
    : <span className="muted">等待自动任务</span> },
  { key: "reported_at", label: "上报时间" },
];

function TaskCenterFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载异常调度任务" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title="当前没有异常调度任务" description="司机上报问题后，系统会自动创建异常与 AI 调度任务。" />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看异常调度任务的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="异常调度任务暂不可用" description="请稍后重试；不会回退到固定案例。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="异常调度任务加载失败" description="请检查服务后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

export function DispatchTaskCenterPage() {
  const auth = useAuth();
  const read = useAnomaliesRead({ limit: 50 });
  const canReview = auth.permissions.includes("dispatch:review");

  return <RoleWorkspaceFrame
    title="异常调度任务"
    description="司机提出问题后，系统自动生成异常记录和 AI 调度任务；此处只展示真实任务，不手工发起固定案例。"
    actions={canReview ? <Link className="secondary-action" to="/reviews">查看待复核</Link> : undefined}
  >
    <WorkspaceSection
      id="anomaly-dispatch-task-center"
      title="任务中心"
      description="点击任务编号查看 8-Agent 处理进度、调度结果与发布状态。"
      actions={read.data ? <span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span> : null}
    >
      {read.state === "READY" && read.data
        ? <DataTable
            caption="异常调度任务列表"
            columns={columns}
            rows={read.data.items}
            rowKey={(item) => String(item.row_id)}
            empty={<span>当前没有异常调度任务。</span>}
          />
        : <TaskCenterFeedback state={read.state} onRetry={read.refresh} />}
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
