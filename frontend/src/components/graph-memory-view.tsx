import { useState } from "react";

import { GraphPathInspector } from "./graph-path-inspector";
import { GraphVisualization } from "./graph-visualization";
import type { GraphMemoryViewModel } from "../types/v2-product";
import { localizeEntityType, localizeStatus } from "../utils/presentation-labels";

const propertyLabels: Record<string, string> = { region: "区域", result: "结果", risk: "风险", severity: "严重程度", status: "状态" };

export function GraphMemoryView({ graph }: { graph: GraphMemoryViewModel }) {
  const [selectedId, setSelectedId] = useState(graph.entities[0]?.id ?? "");
  const selected = graph.entities.find((entity) => entity.id === selectedId) ?? graph.entities[0];
  return <div className="graph-memory-workspace">
    <section className="workspace-panel graph-visual-panel"><div className="panel-heading"><div><p className="eyebrow">NEO4J 图记忆</p><h2>实体关系图</h2></div><span className={`source-label ${graph.provenance === "DEMO_DATA" ? "demo" : "live"}`}>{localizeStatus(graph.provenance)}</span></div>
      {graph.error ? <p className="error-banner">图记忆已降级 · {graph.error}</p> : <div className="graph-layout"><GraphVisualization graph={graph} selectedId={selectedId} onSelect={(entity) => setSelectedId(entity.id)}/><aside className="graph-property-inspector"><p className="eyebrow">节点属性</p><h3>{selected?.label ?? "未选择实体"}</h3><span>{selected?.id ?? "—"}</span><span>{localizeEntityType(selected?.type)}</span>{selected && Object.entries(selected.properties).map(([key, value]) => <div key={key}><small>{propertyLabels[key] ?? key}</small><strong>{typeof value === "string" ? localizeStatus(value) : String(value)}</strong></div>)}</aside></div>}
    </section>
    <GraphPathInspector graph={graph}/>
  </div>;
}
