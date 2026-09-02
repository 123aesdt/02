import { describe, expect, it, vi } from "vitest";

import { createDispatchService } from "../src/services/dispatch-service";
import { graphMemoryFromEventData } from "../src/hooks/use-graph-memory-events";
import { createWorkspaceReadClient } from "../src/services/api/workspace-read-client";

describe("V2 product data contracts", () => {
  it("does not return the mock dashboard snapshot in API mode", async () => {
    const service = createDispatchService({ mode: "api", baseUrl: "http://api.test", fetchImpl: vi.fn() });

    await expect(service.getDashboardSnapshot()).rejects.toThrow("not available in API mode");
  });

  it("returns safe runtime diagnostics from the real health endpoint", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "ok",
      service: "countyflow-backend",
      version: "0.1.0",
      runtime: {
        runtime_profile: "docker-dev",
        database: "mysql",
        redis: "server",
        qdrant: "server",
        graph_memory: "neo4j",
      },
    }), { status: 200 }));
    const service = createDispatchService({ mode: "api", baseUrl: "http://api.test", fetchImpl });

    const health = await service.getBackendHealth();

    expect(health.runtime).toMatchObject({
      database: "mysql",
      redis: "server",
      qdrant: "server",
      graph_memory: "neo4j",
    });
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/health", expect.any(Object));
  });

  it("keeps relation evidence addressable from real graph paths", () => {
    const source = { entity_type: "Driver", entity_id: "driver-li", display_name: "李师傅", properties: {} };
    const target = { entity_type: "Route", entity_id: "xinping-road", display_name: "新平路", properties: {} };
    const fact = { source, target, relation_type: "HAS_RISK_ON", confidence: 0.96, source_type: "Graph Memory", evidence: "historical case", version: 8 };

    const graph = graphMemoryFromEventData({ graph_memory_used: true, graph_memory_facts: [fact], graph_memory_paths: [{ entities: [source, target], relations: [fact] }] });

    expect(graph.paths[0].hopCount).toBe(1);
    expect(graph.relations.find((relation) => relation.id === graph.paths[0].relationIds[0])).toMatchObject({
      type: "HAS_RISK_ON",
      evidence: "historical case",
      controlVersion: 8,
    });
  });

  it("does not synthesize vector-memory provider or model metadata", async () => {
    const response = {
      items: [],
      total: 0,
      next_cursor: null,
      vector_dimension: 128,
      provenance: "LIVE",
    };
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }));
    const client = createWorkspaceReadClient({ baseUrl: "http://api.test", fetchImpl });

    const page = await client.getVectorMemories();

    expect(page).toEqual(response);
    expect(page).not.toHaveProperty("provider");
    expect(page).not.toHaveProperty("model");
  });
});
