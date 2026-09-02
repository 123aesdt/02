import { EmptyState } from "../components/ui/empty-state";
import { StatusBadge } from "../components/ui/status-badge";
import { AuditTimeline } from "../components/workspace/audit-timeline";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { useSecurityAudit } from "../hooks/use-security-audit";
import type { SecurityAuditEvent } from "../services/api/security-audit-client";
import type { ReadState } from "../types/workspace";

export function AuditWorkspace({ state }: { state: ReadState<SecurityAuditEvent[]> }) {
  return <RoleWorkspaceFrame title="审计中心" description="以只读时间线重建身份、决策、干预与变更证据。">
    <WorkspaceSection
      id="audit-timeline"
      title="安全审计时间线"
      description="数据来自 GET /api/v1/security/audit；此工作区只读。"
      actions={<StatusBadge status="LIVE" label="API 投影" />}
    >
      <AuditTimeline state={state} />
    </WorkspaceSection>
    <WorkspaceSection id="audit-projections" title="审计数据范围" description="没有后端契约的聚合不会显示推测值。">
      <div className="audit-projection-grid">
        <EmptyState kind="not-exposed" title="业务决策全局时间线未开放" description="单任务审核证据仍可在任务详情中读取。" />
        <EmptyState kind="not-exposed" title="记忆变更全局时间线未开放" description="当前安全投影仅记录被拦截的记忆变更。" />
        <EmptyState kind="not-exposed" title="运行态干预全局历史未开放" description="任务级干预历史仍以 MySQL 持久记录为准。" />
      </div>
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}

export function AuditPage() {
  return <AuditWorkspace state={useSecurityAudit()} />;
}
