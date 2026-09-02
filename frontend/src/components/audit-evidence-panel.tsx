import type { TaskEvent } from "../types/task-events";
import { localizeAuditCheck, localizeDisplayText, localizeStatus } from "../utils/presentation-labels";

export function AuditEvidencePanel({ events }: { events: TaskEvent[] }) {
  const item = events.filter((event) => event.event_type === "AUDIT_COMPLETED").at(-1);
  if (!item) return null;
  const value = item.data.audit_result;
  const audit = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const checks = audit.checks && typeof audit.checks === "object" ? audit.checks as Record<string, unknown> : {};
  return <section className="audit-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">V2 审核证据</p><h2>{localizeStatus(String(audit.audit_status ?? "—"))}</h2></div><span className="source-label live">实时事件</span></div><p className="audit-evidence-reason">{localizeDisplayText(String(audit.reason ?? "—"))}</p><div className="audit-evidence-checks">{Object.entries(checks).map(([name, passed]) => <span key={name}>{localizeAuditCheck(name)} · {passed === true ? "通过" : "失败"}</span>)}</div><div className="detail-list"><div><span>审核记录</span><strong>审核记录 {String(audit.audit_record_id ?? "—")}</strong></div><div><span>调度记录</span><strong>{String(audit.dispatch_id ?? "—")}</strong></div><div><span>人工复核</span><strong>需要人工复核：{audit.requires_manual_review === true ? "是" : "否"}</strong></div></div></section>;
}
