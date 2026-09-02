import type { RuntimeOverrideDetail } from "../types/runtime-override";
import type { RuntimeCheckpointHistoryItem } from "../types/runtime-thread";
import { localizeEntityType, localizeField, localizeNode, localizeStatus } from "../utils/presentation-labels";

export function CheckpointTimeline({ checkpoints, overrides }: { checkpoints: RuntimeCheckpointHistoryItem[]; overrides: RuntimeOverrideDetail[] }) {
  const items = [
    ...checkpoints.map((item) => ({ kind: "checkpoint" as const, at: item.created_at ?? "", item })),
    ...overrides.map((item) => ({ kind: "override" as const, at: item.completed_at ?? item.requested_at, item })),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return <section className="checkpoint-timeline" aria-label="检查点与运行态干预时间线">
    <div className="panel-heading"><div><p className="eyebrow">持久化执行</p><h2>检查点时间线</h2></div><span>检查点 ID ≠ 状态版本</span></div>
    <div className="checkpoint-timeline-list">{items.length ? items.map((entry) => entry.kind === "checkpoint"
      ? <article key={`checkpoint-${entry.item.checkpoint_id}`} className="checkpoint-entry"><i/><div>
        <strong>智能体检查点 · {localizeNode(entry.item.node)}</strong>
        <span>检查点 ID {entry.item.checkpoint_id}</span>
        <span>检查点状态版本 {entry.item.state_version}</span>
        <small>{entry.item.created_at ?? "时间戳未开放"}</small>
      </div></article>
      : <article key={`override-${entry.item.override_id}`} className="override-entry"><i/><div>
        <strong>运行态干预 · {localizeStatus(entry.item.status)}</strong>
        <span>{localizeEntityType(entry.item.entity_type)} {entry.item.entity_id} · {localizeField(entry.item.field)}：{localizeStatus(entry.item.old_value)} → {localizeStatus(entry.item.new_value)}</span>
        <span>运行态 V{entry.item.before_state_version ?? "—"} → V{entry.item.after_state_version ?? "—"}</span>
        <span>{entry.item.source_checkpoint_id ?? "—"} → {entry.item.result_checkpoint_id ?? "—"}</span>
        <small>{entry.at}</small>
      </div></article>) : <p className="runtime-thread-warning">暂无检查点或干预时间线数据</p>}</div>
  </section>;
}
