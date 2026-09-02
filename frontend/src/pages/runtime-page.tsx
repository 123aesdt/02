import { useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type DataTableColumn } from "../components/ui/data-table";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { useRuntimeThreadsRead } from "../hooks/use-workspace-reads";
import type { RuntimeThreadListItem, WorkspaceReadProvenance } from "../types/workspace-read-models";
import { localizeNode, localizeStatus } from "../utils/presentation-labels";

function provenanceLabel(provenance: WorkspaceReadProvenance) {
  return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据";
}

function runtimeStatusLabel(status: string) {
  if (status === "OVERRIDING") return "干预中";
  if (status === "TERMINAL") return "已结束";
  return localizeStatus(status);
}

function RuntimeReadFeedback({ state, onRetry, paged }: { state: string; onRetry: () => void; paged: boolean }) {
  if (state === "LOADING") return <Skeleton label="正在加载运行线程" lines={6} />;
  if (state === "EMPTY") return <EmptyState kind="empty" title={paged ? "当前筛选页没有运行线程" : "当前没有运行线程"} description="接口已连接，当前分页或筛选范围为空。" action={<button type="button" onClick={onRetry}>重新读取</button>} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看运行线程的权限" description="需要 runtime:read 权限。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="运行线程服务暂不可用" description="请稍后重试；不会回退运行快照正文。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  if (state === "NOT_EXPOSED") return <EmptyState kind="not-exposed" title="运行线程列表未开放" description="当前模式没有批准的运行态读取来源。" />;
  return <EmptyState kind="error" title="运行线程加载失败" description="未显示任何推测状态，请重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

const columns: DataTableColumn<RuntimeThreadListItem>[] = [
  { key: "thread_id", label: "线程" },
  { key: "task_id", label: "任务", render: (item) => <Link to={`/dispatch/${item.task_id}`}>{item.task_id}</Link> },
  { key: "status", label: "状态", render: (item) => <StatusBadge status={item.status} label={runtimeStatusLabel(item.status)} /> },
  { key: "current_node", label: "当前节点", render: (item) => localizeNode(item.current_node) },
  { key: "next_node", label: "下一节点", render: (item) => localizeNode(item.next_node) },
  { key: "state_version", label: "状态版本", render: (item) => `V${item.state_version}` },
  { key: "checkpoint_count", label: "检查点数量" },
  { key: "worker_consumer", label: "工作进程消费者" },
  { key: "terminal_at", label: "终止时间" },
  { key: "updated_at", label: "更新时间" },
];

function ApiRuntimePage() {
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<(string | null)[]>([]);
  const read = useRuntimeThreadsRead({ limit: 20, cursor, status });
  const reset = () => { setCursor(null); setHistory([]); };
  const previous = () => {
    const previousCursor = history.at(-1) ?? null;
    setHistory((items) => items.slice(0, -1));
    setCursor(previousCursor);
  };
  const pagination = history.length ? <div><button type="button" onClick={previous}>上一页</button><button type="button" onClick={reset}>返回首页</button></div> : null;
  const filter = <div className="filters"><label>运行状态<select value={status} onChange={(event) => { setStatus(event.target.value); reset(); }}><option value="">全部状态</option><option value="RUNNING">运行中</option><option value="STABLE">稳定</option><option value="OVERRIDING">干预中</option><option value="TERMINAL">已结束</option></select></label></div>;

  return <RoleWorkspaceFrame title="运行态" description="只读展示批准的线程元数据；不读取或展示运行快照正文。">
    <WorkspaceSection id="runtime-list" title="运行线程" description="全局页不提供强干预；任务治理仅从已知任务详情进入。">
      {filter}
      {read.state === "READY" ? <>
        <div className="panel-heading"><span className={`source-label ${read.data.provenance === "LIVE" ? "live" : "demo"}`}>{provenanceLabel(read.data.provenance)}</span></div>
        <DataTable caption="运行线程安全元数据" columns={columns} rows={read.data.items} rowKey={(item) => String(item.row_id)} />
        {read.data.next_cursor ? <button type="button" onClick={() => { setHistory((items) => [...items, cursor]); setCursor(read.data.next_cursor); }}>下一页</button> : null}
        {pagination}
      </> : <>
        <RuntimeReadFeedback state={read.state} onRetry={read.refresh} paged={history.length > 0} />
        {pagination}
      </>}
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

function MockRuntimePage() {
  return <RoleWorkspaceFrame title="运行态" description="只读展示批准的线程元数据；不读取或展示运行快照正文。">
    <WorkspaceSection id="runtime-list" title="运行线程">
      <EmptyState kind="not-exposed" title="演示模式未提供运行线程列表" description="不会用静态线程或运行快照冒充服务端投影。" />
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

export function RuntimePage() {
  return runtimeConfig.dataMode === "api" ? <ApiRuntimePage /> : <MockRuntimePage />;
}
