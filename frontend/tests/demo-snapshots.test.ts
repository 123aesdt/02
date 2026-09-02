import { describe, expect, it } from "vitest";

import {
  demoAgentSnapshots,
  demoCapabilitySummaries,
  isDemoSnapshotEnabled,
  mergeObservabilityMetrics,
} from "../src/demo/demo-snapshots";

describe("demo snapshot policy", () => {
  it("enables virtual data only for explicit demo runtimes", () => {
    expect(isDemoSnapshotEnabled({ dataMode: "api", authenticationMode: "development_jwt" })).toBe(true);
    expect(isDemoSnapshotEnabled({ dataMode: "mock", authenticationMode: "oidc_jwt" })).toBe(true);
    expect(isDemoSnapshotEnabled({ dataMode: "api", authenticationMode: "oidc_jwt" })).toBe(false);
  });

  it("keeps live telemetry and fills only missing metrics", () => {
    const result = mergeObservabilityMetrics({
      http_qps: 9,
      http_p95: null,
      worker_pending: 0,
    }, true);

    expect(result.metrics.http_qps).toBe(9);
    expect(result.metrics.worker_pending).toBe(0);
    expect(result.demoKeys).not.toContain("http_qps");
    expect(result.demoKeys).not.toContain("worker_pending");
    expect(result.metrics.http_p95).toBe(0.086);
    expect(result.metrics.agent_p95).toBe(0.238);
    expect(result.demoKeys).toEqual(expect.arrayContaining(["http_p95", "agent_p95"]));
  });

  it("does not fill missing telemetry when demo snapshots are disabled", () => {
    const result = mergeObservabilityMetrics({ http_qps: 9, agent_p95: null }, false);

    expect(result.metrics).toEqual({ http_qps: 9, agent_p95: null });
    expect(result.demoKeys).toEqual([]);
  });

  it("provides one consistent catalog for the approved demo surfaces", () => {
    expect(Object.keys(demoCapabilitySummaries)).toEqual([
      "智能体", "记忆", "可观测性", "治理与安全",
    ]);
    expect(demoAgentSnapshots).toHaveLength(8);
    expect(demoAgentSnapshots.map((agent) => agent.id)).toEqual([
      "intake", "entity_memory", "graph_memory", "environment",
      "capacity", "routing", "dispatch", "audit",
    ]);
  });
});
