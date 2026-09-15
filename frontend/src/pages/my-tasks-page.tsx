import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { OperationalSummary } from "../components/workspace/operational-summary";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { isTaskReportable } from "../features/anomaly-report/submission";
import { useMyTasksRead } from "../hooks/use-workspace-reads";
import type { WorkspaceMetric } from "../types/workspace";
import type { MyTaskListItem, MyTaskQueueState, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

interface MyTaskTableRow extends MyTaskListItem { route_direction?: never; publication?: never; details?: never }

const columns: DataTableColumn<MyTaskTableRow>[] = [
  { key: "task_id", label: "任务" },
  { key: "order_no", label: "运单" },
  { key: "risk", label: "风险", render: (item) => localizeStatus(item.risk) },
  { key: "description", label: "任务说明" },
  { key: "vehicle_id", label: "车辆" },
  { key: "suggested_route_id", label: "下发路线", render: (item) => item.publication_status === "PUBLISHED" ? item.suggested_route_id ?? "—" : "等待主管发布" },
  { key: "route_direction", label: "行驶方向", render: (item) => `${item.origin ?? "—"} → ${item.destination ?? "—"}` },
  { key: "route_instruction", label: "行驶说明", render: (item) => item.route_instruction ?? "路线发布后显示" },
  { key: "publication", label: "发布状态", render: (item) => {
    const publicationStatus = item.publication_status ?? "PENDING";
    return <StatusBadge status={publicationStatus} label={publicationStatus === "PUBLISHED" ? "已发布" : "待发布"} />;
  } },
  { key: "status", label: "状态", render: (item) => <StatusBadge status={item.status} label={localizeStatus(item.status)} /> },
  { key: "updated_at", label: "最近更新" },
  { key: "details", label: "操作", render: (item) => <div className="task-row-actions">
    <Link className="inline-link" to={`/dispatch/${item.task_id}`}>查看详情</Link>
    {item.can_report_anomaly && isTaskReportable(item.status) ? <Link className="inline-link" to={`/report-issue?taskId=${encodeURIComponent(item.task_id)}`}>报告问题</Link> : null}
  </div> },
];

const filters: readonly { value: MyTaskQueueState | null; label: string }[] = [
  { value: null, label: "全部" },
  { value: "READY", label: "待执行" },
  { value: "WAITING", label: "等待中" },
  { value: "ACTIVE", label: "处理中" },
  { value: "ENDED", label: "已结束" },
];

function MyTaskFeedback({ state, onRetry, paged }: { state: string; onRetry: () => void; paged: boolean }) {
  if (state === "LOADING") return <Skeleton label="正在加载我的任务" lines={5} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title={paged ? "当前分页没有任务" : "当前账号还没有分配任务"} description="接口已连接，系统只展示分配给当前员工的任务。" action={<button type="button" onClick={onRetry}>重新读取</button>} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看我的任务的权限" description="需要 dispatch:read 权限。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="我的任务服务暂不可用" description="请稍后重试；不会回退到静态任务。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "NOT_EXPOSED") return <EmptyState kind="not-exposed" title="我的任务未开放" description="当前运行模式没有已批准的员工任务读取来源。" />;
  return <EmptyState kind="error" title="我的任务加载失败" description="没有显示任何推测任务，请重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

export function MyTasksPage() {
  const [state, setState] = useState<MyTaskQueueState | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const read = useMyTasksRead({ limit: 20, cursor, state: state ?? undefined });

  const metrics = useMemo<WorkspaceMetric[]>(() => {
    const summary = read.data?.summary;
    return [
      { id: "total", label: "全部任务", value: summary ? String(summary.total) : null, provenance: read.data?.provenance ?? "NOT_EXPOSED" },
      { id: "ready", label: "待执行", value: summary ? String(summary.ready) : null, provenance: read.data?.provenance ?? "NOT_EXPOSED" },
      { id: "waiting", label: "等待中", value: summary ? String(summary.waiting) : null, provenance: read.data?.provenance ?? "NOT_EXPOSED" },
      { id: "active", label: "处理中", value: summary ? String(summary.active) : null, provenance: read.data?.provenance ?? "NOT_EXPOSED" },
      { id: "ended", label: "已结束", value: summary ? String(summary.ended) : null, provenance: read.data?.provenance ?? "NOT_EXPOSED" },
    ];
  }, [read.data]);

  const selectState = (next: MyTaskQueueState | null) => {
    setState(next);
    setCursor(null);
    setHistory([]);
  };

  const previous = () => {
    const prior = history.at(-1) ?? null;
    setHistory((items) => items.slice(0, -1));
    setCursor(prior);
  };

  return <RoleWorkspaceFrame
    title="我的任务"
    description="查看只属于当前员工的待执行、等待、处理及已结束任务。"
    actions={<Link className="primary-action" to="/report-issue">提出问题</Link>}
  >
    <OperationalSummary title="任务概览" metrics={metrics} />
    <WorkspaceSection
      id="my-task-queue"
      title="任务队列"
      description="任务归属由服务端身份确认；切换员工后只会读取对应员工的数据。"
      actions={read.data ? <span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span> : null}
    >
      <div className="task-state-filters" aria-label="任务状态筛选">
        {filters.map((filter) => <button
          key={filter.value ?? "ALL"}
          type="button"
          className={state === filter.value ? "active" : undefined}
          aria-pressed={state === filter.value}
          onClick={() => selectState(filter.value)}
        >{filter.label}</button>)}
      </div>
      {read.state === "READY" && read.data ? <>
        <DataTable caption="我的任务队列" columns={columns} rows={read.data.items} rowKey={(item) => String(item.row_id)} empty={<span>当前筛选条件下没有任务。</span>} />
        <div className="task-pagination">
          {history.length > 0 ? <button type="button" onClick={previous}>上一页</button> : null}
          {read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}
        </div>
      </> : <MyTaskFeedback state={read.state} onRetry={read.refresh} paged={history.length > 0} />}
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
