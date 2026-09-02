import { ProjectionStatus } from "./projection-status";
import type { GraphMemoryViewModel } from "../types/v2-product";
import { localizeRelationType } from "../utils/presentation-labels";

export function GraphPathInspector({ graph }: { graph: GraphMemoryViewModel }) {
  const entities = new Map(graph.entities.map((entity) => [entity.id, entity]));
  const relations = new Map(graph.relations.map((relation) => [relation.id, relation]));
  return <section className="graph-path-panel"><div className="panel-heading compact"><div><p className="eyebrow">有界多跳查询</p><h3>路径检查</h3></div><span>{graph.paths.length} 条路径</span></div>
    <div className="graph-path-list">{graph.paths.map((path) => <article key={path.id}><div className="graph-path-title"><strong>{path.entityIds.map((id) => entities.get(id)?.label ?? id).join(" → ")}</strong><span>跳数 {path.hopCount}</span></div><ol>{path.relationIds.map((id) => { const relation = relations.get(id); return relation ? <li key={id}><b>{localizeRelationType(relation.type)}</b><span>置信度 {(relation.confidence * 100).toFixed(1)}%</span><span>{relation.source}</span><span>{relation.evidence}</span><span>控制版本 v{relation.controlVersion}</span><ProjectionStatus status={relation.projectionStatus}/></li> : null; })}</ol></article>)}</div>
  </section>;
}
