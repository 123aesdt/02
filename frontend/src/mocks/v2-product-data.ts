import type { GraphMemoryViewModel, VerifiedMetric } from "../types/v2-product";
import type { SharedMemoryFactDetail } from "../types/memory";

export const verifiedV2Metrics: VerifiedMetric[] = [
  { label: "向量 Top-1", value: "49 / 50 · 98%", detail: "Qwen3-Embedding-4B · 2560 维", group: "memory" },
  { label: "向量 Top-3", value: "50 / 50 · 100%", detail: "最新 V2-E 回归", group: "memory" },
  { label: "图记忆召回", value: "20 / 20", detail: "P95 10.354ms", group: "memory" },
  { label: "共享记忆", value: "0 次更新丢失", detail: "0 次投影泄漏", group: "reliability" },
  { label: "运行态干预", value: "50 / 50", detail: "0 / 50 次下游陈旧读取", group: "runtime" },
  { label: "检查点恢复", value: "5 / 5", detail: "Worker 最长恢复时间 4.824s", group: "runtime" },
  { label: "Redis 消息丢失", value: "0", detail: "V2-E Worker 恢复证据", group: "reliability" },
  { label: "负载验收", value: "QPS ≥ 400.071", detail: "P95 ≤ 200ms · 错误率 0%", group: "performance" },
  { label: "黑盒验收", value: "15 / 15 通过", detail: "V2-E 最终验收", group: "reliability" },
];

export const demoGraphMemory: GraphMemoryViewModel = {
  provenance: "DEMO_DATA",
  used: true,
  elapsedMs: 10.354,
  error: null,
  entities: [
    { id: "driver-li", type: "Driver", label: "李师傅", properties: { region: "新平县" } },
    { id: "vehicle-cold-a", type: "Vehicle", label: "冷链车A", properties: { status: "NORMAL" } },
    { id: "xinping-road", type: "Route", label: "新平路", properties: { risk: "HIGH" } },
    { id: "rain", type: "Weather", label: "Rain", properties: { severity: "HEAVY" } },
    { id: "national-102", type: "Route", label: "102国道", properties: { risk: "LOW" } },
    { id: "rain-risk", type: "Anomaly", label: "雨天道路湿滑", properties: { status: "ACTIVE" } },
    { id: "reroute-102", type: "Resolution", label: "改走102国道", properties: { result: "VERIFIED" } },
  ],
  relations: [
    { id: "r1", sourceId: "driver-li", targetId: "vehicle-cold-a", type: "DRIVES", confidence: 0.99, source: "MySQL projection", evidence: "driver assignment", controlVersion: 8, projectionStatus: "ACTIVE" },
    { id: "r2", sourceId: "driver-li", targetId: "xinping-road", type: "HAS_RISK_ON", confidence: 0.96, source: "Graph Memory", evidence: "historical rain case", controlVersion: 8, projectionStatus: "ACTIVE" },
    { id: "r3", sourceId: "xinping-road", targetId: "rain", type: "HIGH_RISK_WHEN", confidence: 0.98, source: "Graph Memory", evidence: "road-weather relation", controlVersion: 8, projectionStatus: "ACTIVE" },
    { id: "r4", sourceId: "national-102", targetId: "xinping-road", type: "ALTERNATIVE_TO", confidence: 0.94, source: "Graph Memory", evidence: "verified reroute", controlVersion: 8, projectionStatus: "ACTIVE" },
    { id: "r5", sourceId: "rain-risk", targetId: "reroute-102", type: "RESOLVED_BY", confidence: 0.95, source: "Audit evidence", evidence: "APPROVED dispatch", controlVersion: 8, projectionStatus: "ACTIVE" },
  ],
  paths: [
    { id: "path-driver-alternative", entityIds: ["driver-li", "xinping-road", "national-102"], relationIds: ["r2", "r4"], hopCount: 2 },
    { id: "path-weather-risk", entityIds: ["driver-li", "xinping-road", "rain"], relationIds: ["r2", "r3"], hopCount: 2 },
  ],
};

export const demoSharedMemoryFact: SharedMemoryFactDetail = {
  fact_key: "smf_vehicle_a_status",
  category: "DispatchMemory",
  fact_kind: "ATTRIBUTE",
  subject_type: "Vehicle",
  subject_id: "vehicle-a",
  predicate: "STATUS",
  object_type: null,
  object_id: null,
  version: 8,
  confidence: "0.9900",
  status: "ACTIVE",
  expires_at: null,
  vector_memory_id: "memory-vehicle-a-status",
  graph_fact_key: "Vehicle:vehicle-a:STATUS",
  last_mutation_id: "mutation-8",
  updated_at: "2026-08-27T01:01:00Z",
  value_json: { status: "BROKEN" },
  projection_incomplete: true,
  mutations: [
    { mutation_id: "mutation-8", decision: "REPLACE", status: "FINALIZING", before_version: 7, after_version: 8, vector_status: "STAGED", graph_status: "ACTIVE", reason_code: "HUMAN_CONFIRMED", error_code: null, error_summary: null, source_type: "operator", source_id: "ops-console", operator_id: "operator-1", incoming_confidence: "0.9900", created_at: "2026-08-27T01:00:00Z", completed_at: null },
    { mutation_id: "mutation-7", decision: "CREATE", status: "APPLIED", before_version: null, after_version: 7, vector_status: "ACTIVE", graph_status: "ACTIVE", reason_code: "NEW_FACT", error_code: null, error_summary: null, source_type: "worker", source_id: "worker-county-01", operator_id: "system", incoming_confidence: "0.9500", created_at: "2026-08-27T00:30:00Z", completed_at: "2026-08-27T00:30:01Z" },
  ],
  evidence: [],
};
