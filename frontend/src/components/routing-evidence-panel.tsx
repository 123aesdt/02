import type { TaskEvent } from "../types/task-events";
import { localizeDisplayText, localizeStatus } from "../utils/presentation-labels";

export function RoutingEvidencePanel({ events }: { events: TaskEvent[] }) {
  const item = events.filter((event) => event.event_type === "ROUTING_COMPLETED").at(-1);
  if (!item) return null;
  const data = item.data;
  const candidates = Array.isArray(data.candidate_routes) ? data.candidate_routes.filter((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object") : [];
  const excluded = candidates.filter((candidate) => candidate.available === false);
  return <section className="routing-evidence-panel"><div className="panel-heading"><div><p className="eyebrow">路线规划证据</p><h2>{localizeStatus(String(data.decision ?? "—"))}</h2></div><span className="source-label live">实时事件</span></div><div className="detail-list"><div><span>最终决策</span><strong>{String(data.recommended_route ?? "—")}</strong></div><div><span>运力约束</span><strong>{localizeDisplayText(String(data.decision_reason ?? "—"))}</strong></div><div><span>人工复核</span><strong>{data.requires_manual_review === true ? "是" : "否"}</strong></div></div><h3>候选路线</h3><div className="routing-candidate-list">{candidates.map((candidate) => <span key={String(candidate.route_id)}><b>{String(candidate.route_name ?? candidate.route_id)}</b><small>{candidate.available === false ? "已排除" : "可用"} · 评分 {String(candidate.score ?? "—")}</small></span>)}</div><h3>已排除资源</h3>{excluded.length ? excluded.map((candidate) => <p key={String(candidate.route_id)} className="excluded-resource">{localizeDisplayText(String(candidate.reason ?? `${String(candidate.route_name ?? candidate.route_id)} 不可用`))}</p>) : <p className="api-disclaimer">后端未返回已排除资源。</p>}</section>;
}
