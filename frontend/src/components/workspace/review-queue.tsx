import { DataTable } from "../ui/data-table";
import { EmptyState } from "../ui/empty-state";
import { StatusBadge } from "../ui/status-badge";

export interface ReviewTask {
  taskId: string;
  aiDecision: string;
  risk: string;
  reason: string;
  vehicle: string;
  route: string;
  state: string;
  waitTime: string;
}

export function ReviewQueue({ tasks }: { tasks: readonly ReviewTask[] }) {
  return <DataTable
    caption="待人工复核队列"
    columns={[
      { key: "taskId", label: "任务" },
      { key: "aiDecision", label: "AI 决策" },
      { key: "risk", label: "风险" },
      { key: "reason", label: "原因" },
      { key: "vehicle", label: "车辆" },
      { key: "route", label: "路线" },
      { key: "state", label: "状态", render: (task) => <StatusBadge status={task.state} /> },
      { key: "waitTime", label: "等待时间" },
    ]}
    rows={[...tasks]}
    rowKey={(task) => task.taskId}
    empty={<EmptyState kind="not-exposed" title="复核队列接口尚未开放" description="复核操作接口尚未开放；没有已批准的读取与动作契约，因此不模拟确认或拒绝。" />}
  />;
}
