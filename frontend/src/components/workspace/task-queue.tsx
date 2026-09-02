import { Link } from "react-router-dom";

import { DataTable } from "../ui/data-table";
import { EmptyState } from "../ui/empty-state";
import { StatusBadge } from "../ui/status-badge";
import type { WorkspaceTask } from "../../types/workspace";
import { localizeStatus } from "../../utils/presentation-labels";

export function TaskQueue({
  tasks,
  unavailableMessage,
  emptyTitle = "当前没有待处理任务",
}: {
  tasks: readonly WorkspaceTask[];
  unavailableMessage?: string;
  emptyTitle?: string;
}) {
  return <DataTable
    caption="任务队列"
    columns={[
      { key: "taskId", label: "任务", render: (task) => task.detailHref ? <Link className="inline-link" to={task.detailHref}>{task.taskId}</Link> : task.taskId },
      { key: "title", label: "事项" },
      { key: "risk", label: "风险", render: (task) => localizeStatus(task.risk) },
      { key: "waitingSince", label: "最近更新" },
      { key: "status", label: "状态", render: (task) => <StatusBadge status={task.status} label={localizeStatus(task.status)} /> },
    ]}
    rows={[...tasks]}
    rowKey={(task) => task.taskId}
    empty={<EmptyState
      kind={unavailableMessage ? "not-exposed" : "empty"}
      title={unavailableMessage ?? emptyTitle}
      description={unavailableMessage ? "没有服务端归属数据时不会显示零任务。" : undefined}
    />}
  />;
}
