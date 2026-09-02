# Memory Benchmark Acceptance

Date: 2026-08-26. Status: VERIFIED.

## Runtime

- Provider: existing OpenAI-Compatible EmbeddingProvider
- Base host: `api.siliconflow.cn` (API key omitted)
- Model: `Qwen/Qwen3-Embedding-4B`
- Confirmed response dimension: 2,560
- Qdrant: real server
- Independent collection: `entity_resolution_memory_benchmark`
- Collection points: 10

The initially configured dimension was 1,024. A real provider response proved the model returns 2,560 dimensions; no truncation or padding was used. The independent benchmark collection was recreated at the confirmed dimension, leaving the 128-dimensional Docker functional collection unchanged.

## Dataset and representation

- Queries: 50, unchanged
- Memories: 10, unchanged
- Memory embedding text: `司机 {driver_id} 路线 {route_id} 异常 {anomaly_type} 解决方案 {resolution_text} {metadata.text}`
- Query embedding text: the unchanged raw benchmark query
- Ranking: Qdrant cosine-similarity Top-K, without ID lookup or manual reranking

## Formal result

| Metric | Result | Requirement | Status |
|---|---:|---:|---|
| Top-1 | 49/50 (98%) | >=46/50 (92%) | PASS |
| Top-3 | 50/50 (100%) | Informational | PASS |
| Failed queries | 1 | — | Recorded |

Failed query:

| Query ID | Query | Expected | Actual Top-1 | Score | Top-3 |
|---|---|---|---|---:|---|
| query-045 | 当前是冷藏温控问题而非普通电量不足，找对应经验 | memory-cold-zheng | memory-battery-sun | 0.57240146 | memory-battery-sun, memory-cold-zheng, memory-capacity-zhou |

Memory adoption remains 4/4 valid cases (100%); all 3 invalid cases remained unadopted.

Machine-readable evidence: `raw/memory-benchmark-results.json` and `raw/memory-benchmark-results.csv`.
