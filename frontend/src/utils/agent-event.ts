function evidenceValue(data: Record<string, unknown>, key: string): string | null {
  const value = data[key];
  return value == null || typeof value === "object" ? null : String(value);
}

export function describeAgentEvent(agentId: string, eventType: string, data: Record<string, unknown>): string {
  if (agentId === "graph_memory") {
    const facts = Array.isArray(data.graph_memory_facts) ? data.graph_memory_facts.length : 0;
    const paths = Array.isArray(data.graph_memory_paths) ? data.graph_memory_paths.length : 0;
    return `${eventType} · ${facts} 条事实 · ${paths} 条路径`;
  }
  const keysByAgent: Record<string, string[]> = {
    entity_memory: ["memory_id", "recommendation"],
    environment: ["environment_risk", "fallback_reason"],
    capacity: ["vehicle_status", "capacity_status"],
    routing: ["recommended_route", "decision"],
    dispatch: ["status", "route"],
    audit: ["result", "reason"],
  };
  const highlights = (keysByAgent[agentId] ?? []).map((key) => evidenceValue(data, key)).filter((value): value is string => Boolean(value));
  return highlights.length ? `${eventType} · ${highlights.join(" · ")}` : eventType;
}
