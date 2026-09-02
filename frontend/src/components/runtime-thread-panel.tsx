import type { RuntimeThreadClient } from "../services/api/runtime-thread-client";
import { useRuntimeThread, type RuntimeThreadViewState } from "../hooks/use-runtime-thread";
import { localizeNode, localizeStatus } from "../utils/presentation-labels";

function Row({ label, value }: { label: string; value: string }) {
  return <div className="runtime-thread-row"><span>{label}</span><strong>{value}</strong></div>;
}

export function RuntimeThreadPanel({
  taskId,
  enabled,
  client,
  refreshKey = 0,
  state,
}: {
  taskId: string;
  enabled: boolean;
  client?: RuntimeThreadClient;
  refreshKey?: number;
  state?: RuntimeThreadViewState;
}) {
  const internalState = useRuntimeThread(taskId, enabled && state === undefined, client, refreshKey);
  const viewState = state ?? internalState;
  if (viewState.kind === "disabled") return null;
  if (viewState.kind === "loading") return <section className="runtime-thread-panel"><p>正在读取运行线程…</p></section>;
  if (viewState.kind === "unauthorized") return <section className="runtime-thread-panel"><p>无权查看运行线程</p></section>;
  if (viewState.kind === "unavailable") return <section className="runtime-thread-panel"><p>运行线程暂时不可用</p></section>;

  const { detail, history } = viewState;
  return <section className="runtime-thread-panel" aria-label="运行线程">
    <div className="panel-heading"><div><p className="eyebrow">持久运行状态</p><h2>运行线程</h2></div><span className="runtime-thread-status">{localizeStatus(detail.status)}</span></div>
    <div className="detail-list">
      <Row label="线程 ID" value={detail.thread_id}/>
      <Row label="状态版本" value={String(detail.state_version)}/>
      <Row label="当前检查点" value={detail.current_checkpoint_id ?? "—"}/>
      <Row label="节点" value={`${detail.current_node ?? "—"} → ${detail.next_node ?? "END"}`}/>
      <Row label="检查点数量" value={String(detail.checkpoint_count)}/>
      <Row label="Worker 消费者" value={detail.worker_consumer ?? "—"}/>
      <Row label="更新时间" value={detail.updated_at}/>
    </div>
    {!detail.checkpoint_available ? <p className="runtime-thread-warning">检查点已过期或不可用</p> : null}
    <div className="runtime-thread-history">
      <p className="eyebrow">检查点时间线</p>
      {history.items.slice(0, 20).map((item) => <div className="runtime-thread-history-item" key={item.checkpoint_id}>
        <span>智能体检查点 · {localizeNode(item.node)}</span><code>检查点 ID {item.checkpoint_id}</code><small>检查点状态版本 {item.state_version}</small>
      </div>)}
    </div>
  </section>;
}
