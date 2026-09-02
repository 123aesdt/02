import type { RuntimeOverrideHistory } from "../types/runtime-override";
import { localizeEntityType, localizeField, localizeStatus } from "../utils/presentation-labels";

export function RuntimeOverrideHistoryPanel({ history }: { history: RuntimeOverrideHistory | null }) {
  return <section className="runtime-override-history"><p className="eyebrow">干预历史</p><h2>干预审计</h2>
    {!history?.items.length ? <p>暂无干预记录</p> : history.items.slice(0, 5).map((item) => <article key={item.override_id} data-override-id={item.override_id}>
      <strong>{localizeStatus(item.status)} · {item.operator_id}（{item.operator_role === "dispatcher" ? "调度员" : item.operator_role}）</strong><span>{localizeEntityType(item.entity_type)} {item.entity_id} · {localizeField(item.field)}</span><span>{localizeStatus(item.old_value)} → {localizeStatus(item.new_value)}</span><span>{item.reason}</span><span>运行态 V{item.before_state_version ?? "—"} → V{item.after_state_version ?? "—"}</span><span>{item.source_checkpoint_id ?? "—"} → {item.result_checkpoint_id ?? "—"}</span><time>{item.completed_at ?? item.requested_at}</time>
    </article>)}
  </section>;
}
