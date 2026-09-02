import { useCallback, useMemo } from "react";

import { runtimeConfig } from "../config/runtime";
import { demoGraphMemory } from "../mocks/v2-product-data";
import type { GraphEntityView, GraphMemoryViewModel, GraphRelationView } from "../types/v2-product";
import { useTaskEvents } from "./use-task-events";

const entityTypes = new Set(["Driver", "Vehicle", "Route", "Weather", "Anomaly", "Resolution"]);
const relationTypes = new Set(["DRIVES", "HAS_RISK_ON", "HIGH_RISK_WHEN", "ALTERNATIVE_TO", "RESOLVED_BY"]);

function entity(value: unknown): GraphEntityView | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  const type = String(raw.entity_type ?? "Anomaly");
  const id = String(raw.entity_id ?? raw.display_name ?? "unknown");
  return { id, type: (entityTypes.has(type) ? type : "Anomaly") as GraphEntityView["type"], label: String(raw.display_name ?? id), properties: typeof raw.properties === "object" && raw.properties !== null ? raw.properties as Record<string, unknown> : {} };
}

export function graphMemoryFromEventData(data: Record<string, unknown>): GraphMemoryViewModel {
  const facts = Array.isArray(data.graph_memory_facts) ? data.graph_memory_facts : [];
  const entities = new Map<string, GraphEntityView>();
  const relations: GraphRelationView[] = [];
  const addRelation = (factValue: unknown, id: string): string | null => {
    if (!factValue || typeof factValue !== "object") return null;
    const fact = factValue as Record<string, unknown>; const source = entity(fact.source); const target = entity(fact.target);
    if (!source || !target) return null;
    entities.set(source.id, source); entities.set(target.id, target);
    const relationType = String(fact.relation_type ?? "HAS_RISK_ON");
    relations.push({ id, sourceId: source.id, targetId: target.id, type: (relationTypes.has(relationType) ? relationType : "HAS_RISK_ON") as GraphRelationView["type"], confidence: Number(fact.confidence ?? 0), source: String(fact.source_type ?? "Graph Memory"), evidence: String(fact.evidence ?? "—"), controlVersion: Number(fact.version ?? 0), projectionStatus: String(fact.projection_status ?? "ACTIVE") });
    return id;
  };
  facts.forEach((factValue, index) => { addRelation(factValue, `event-relation-${index}`); });
  const rawPaths = Array.isArray(data.graph_memory_paths) ? data.graph_memory_paths : [];
  const paths = rawPaths.map((pathValue, index) => {
    const path = pathValue && typeof pathValue === "object" ? pathValue as Record<string, unknown> : {};
    const pathEntities = Array.isArray(path.entities) ? path.entities.map(entity).filter((item): item is GraphEntityView => Boolean(item)) : [];
    pathEntities.forEach((item) => entities.set(item.id, item));
    const pathFacts = Array.isArray(path.relations) ? path.relations : [];
    const relationIds = pathFacts.map((fact, relationIndex) => addRelation(fact, `event-path-${index}-relation-${relationIndex}`)).filter((id): id is string => Boolean(id));
    return { id: `event-path-${index}`, entityIds: pathEntities.map((item) => item.id), relationIds, hopCount: relationIds.length };
  });
  return { provenance: "LIVE_EVENT", used: data.graph_memory_used === true, elapsedMs: data.graph_memory_elapsed_ms == null ? null : Number(data.graph_memory_elapsed_ms), error: data.graph_memory_error ? String(data.graph_memory_error) : null, entities: [...entities.values()], relations, paths };
}

export function useGraphMemoryEvents(taskId: string): { graph: GraphMemoryViewModel; connection: string } {
  const onTerminal = useCallback(() => undefined, []);
  const { events, connection } = useTaskEvents(taskId, onTerminal);
  return useMemo(() => {
    if (runtimeConfig.dataMode === "mock") return { graph: demoGraphMemory, connection: "DEMO" };
    const graphEvent = [...events].reverse().find((event) => event.event_type === "GRAPH_MEMORY_COMPLETED" || event.event_type === "GRAPH_MEMORY_DEGRADED");
    return { graph: graphEvent ? graphMemoryFromEventData(graphEvent.data) : { provenance: "LIVE_EVENT", used: false, elapsedMs: null, error: null, entities: [], relations: [], paths: [] }, connection };
  }, [connection, events]);
}
