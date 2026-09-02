import type { TaskEvent } from "../types/task-events";
import { localizeStatus } from "../utils/presentation-labels";

function uniqueOrdered(events: TaskEvent[]): TaskEvent[] {
  const seen = new Set<string>();
  return [...events].sort((a, b) => a.sequence - b.sequence).filter((item) => !seen.has(item.event_id) && seen.add(item.event_id)).slice(-30);
}

function semanticLabel(item: TaskEvent): string {
  const data = item.data;
  if (item.event_type === "ENVIRONMENT_COMPLETED") return "环境节点已完成";
  if (item.event_type === "THREAD_CHECKPOINTED") return "检查点已提升";
  if (item.event_type === "RUNTIME_OVERRIDE_REQUESTED") return "已请求运行态干预";
  if (item.event_type === "RUNTIME_OVERRIDE_APPLIED") return `车辆 ${localizeStatus(String(data.old_value ?? "—"))} → ${localizeStatus(String(data.new_value ?? "—"))}`;
  if (item.event_type === "CAPACITY_STARTED") return "运力节点已开始";
  if (item.event_type === "CAPACITY_COMPLETED") return `运力读取到${localizeStatus(String(data.vehicle_status ?? "—"))}${data.vehicle_available === false ? " · 车辆不可用" : ""}`;
  if (item.event_type === "ROUTING_COMPLETED") return `路线已重新计算 · ${localizeStatus(String(data.decision ?? "—"))}`;
  if (item.event_type === "AUDIT_COMPLETED") {
    const audit = data.audit_result && typeof data.audit_result === "object" ? data.audit_result as Record<string, unknown> : {};
    return `审核已记录 · ${localizeStatus(String(audit.audit_status ?? "—"))}`;
  }
  return item.event_type.replaceAll("_", " ").toLowerCase().replace(/^./, (value) => value.toUpperCase());
}

export function RuntimeEventTimeline({ events }: { events: TaskEvent[] }) {
  return <section className="runtime-event-timeline"><p className="eyebrow">运行态时间线</p><h2>运行事件</h2>{uniqueOrdered(events).map((item) => {
    const data = item.data;
    return <article key={item.event_id} data-event-id={item.event_id}><strong>{semanticLabel(item)}</strong><small>{item.event_type}</small>
      {data.operator_id ? <span>{String(data.operator_id)} · {String(data.reason ?? "—")}</span> : null}
      {data.old_value ? <span>{localizeStatus(String(data.old_value))} → {localizeStatus(String(data.new_value))}</span> : null}
      {data.before_state_version !== undefined ? <span>V{String(data.before_state_version)} → V{String(data.after_state_version)}</span> : null}
    </article>;
  })}</section>;
}
