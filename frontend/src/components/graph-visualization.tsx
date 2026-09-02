import type { GraphEntityView, GraphMemoryViewModel } from "../types/v2-product";
import { localizeEntityType, localizeRelationType } from "../utils/presentation-labels";

const positions: Record<string, { x: number; y: number }> = {
  "driver-li": { x: 12, y: 18 }, "vehicle-cold-a": { x: 42, y: 8 }, "xinping-road": { x: 42, y: 42 },
  rain: { x: 76, y: 18 }, "national-102": { x: 76, y: 58 }, "rain-risk": { x: 12, y: 72 }, "reroute-102": { x: 48, y: 78 },
};

export function GraphVisualization({ graph, selectedId, onSelect }: { graph: GraphMemoryViewModel; selectedId: string; onSelect: (entity: GraphEntityView) => void }) {
  const entityById = new Map(graph.entities.map((entity) => [entity.id, entity]));
  return <div className="graph-canvas" aria-label="实体关系图">
    <svg viewBox="0 0 100 100" role="img" aria-label="图记忆实体关系">
      <defs><marker id="graph-arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0,0 L5,2.5 L0,5 Z" /></marker></defs>
      {graph.relations.map((relation) => {
        const source = positions[relation.sourceId]; const target = positions[relation.targetId];
        if (!source || !target || !entityById.has(relation.sourceId) || !entityById.has(relation.targetId)) return null;
        return <g key={relation.id}><line x1={source.x + 5} y1={source.y + 4} x2={target.x + 5} y2={target.y + 4} markerEnd="url(#graph-arrow)"/><text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 2}>{localizeRelationType(relation.type)}</text></g>;
      })}
    </svg>
    {graph.entities.map((entity, index) => {
      const position = positions[entity.id] ?? { x: 10 + (index % 3) * 32, y: 10 + Math.floor(index / 3) * 34 };
      return <button key={entity.id} type="button" aria-label={`选择图节点 ${entity.label}`} aria-pressed={selectedId === entity.id} className={`graph-node graph-node-${entity.type.toLowerCase()} ${selectedId === entity.id ? "selected" : ""}`} style={{ left: `${position.x}%`, top: `${position.y}%` }} onMouseEnter={() => onSelect(entity)} onFocus={() => onSelect(entity)} onClick={() => onSelect(entity)}><small>{localizeEntityType(entity.type)}</small><strong>{entity.label}</strong></button>;
    })}
  </div>;
}
