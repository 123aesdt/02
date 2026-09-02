import type { SecurityAuditEvent } from "../../services/api/security-audit-client";
import type { ReadState } from "../../types/workspace";
import { DataTable, type DataTableColumn } from "../ui/data-table";
import { EmptyState } from "../ui/empty-state";
import { Skeleton } from "../ui/skeleton";
import { StatusBadge } from "../ui/status-badge";

const eventLabels: Record<string, string> = {
  REVIEW_DECISION: "人工复核决定",
};

const reasonLabels: Record<string, string> = {
  REVIEW_APPROVED: "人工复核已批准",
  REVIEW_REJECTED: "人工复核已拒绝",
};

const columns: DataTableColumn<SecurityAuditEvent>[] = [
  { key: "created_at", label: "时间", render: (row) => new Date(row.created_at).toLocaleString("zh-CN", { hour12: false }) },
  { key: "event_type", label: "事件", render: (row) => eventLabels[row.event_type] ?? row.event_type },
  { key: "status", label: "状态", render: (row) => <StatusBadge status={row.status} /> },
  { key: "subject_id", label: "主体" },
  { key: "permission", label: "权限" },
  { key: "route_template", label: "路由" },
  { key: "reason_code", label: "原因", render: (row) => reasonLabels[row.reason_code] ?? row.reason_code },
  { key: "request_id", label: "请求 ID" },
];

function stateContent(state: Exclude<ReadState<SecurityAuditEvent[]>, { state: "READY" }>) {
  if (state.state === "LOADING") return <Skeleton label="正在读取安全审计事件" lines={4} />;
  if (state.state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有审计读取权限" description="需要 audit:read 权限。" />;
  if (state.state === "NOT_EXPOSED") return <EmptyState kind="not-exposed" title="审计投影未开放" description={state.message} />;
  if (state.state === "EMPTY") return <EmptyState kind="empty" title="当前没有安全审计事件" description="接口已连接，最近事件列表为空。" />;
  return <EmptyState kind="unavailable" title="安全审计暂时不可用" description="未显示任何推测事件。" />;
}

export function AuditTimeline({ state }: { state: ReadState<SecurityAuditEvent[]> }) {
  return <DataTable
    caption="最近 100 条安全审计事件（只读）"
    columns={columns}
    rows={state.state === "READY" ? state.data : []}
    rowKey={(row) => row.event_id}
    loading={state.state === "LOADING" ? stateContent(state) : undefined}
    empty={state.state !== "READY" && state.state !== "LOADING" ? stateContent(state) : undefined}
  />;
}
