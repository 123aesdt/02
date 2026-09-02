# V2-E Performance Acceptance

Status: **PARTIAL — external Embedding regression blocked by host policy**

## Verified

- Graph warm query: 50 samples, p95 10.354ms (<150ms).
- Runtime override: 50 samples, p95 181.643ms.
- Locust V2 mixed workload, 50 users, spawn rate 25/s, three 60-second runs:

| Run | Requests | QPS | P50 | P95 | P99 | Errors | Graph P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 23,697 | 400.071 | 78ms | 190ms | 260ms | 0% | 9ms |
| 2 | 24,955 | 420.842 | 70ms | 200ms | 280ms | 0% | 9ms |
| 3 | 25,016 | 422.349 | 71ms | 190ms | 280ms | 0% | 8ms |

The workload includes health, task submit/status/result, Runtime Thread GET, Runtime Override POST, real Qdrant query, bounded real Neo4j query, and low-weight isolated Shared Memory mutation.

## Not verified

The required Qwen/Qwen3-Embedding-4B regression could not execute because the host denied exporting the fixed benchmark text to the configured `api.siliconflow.cn` endpoint with the private key. The required baseline (Top-1 49/50 and Top-3 50/50) is therefore not reused as current evidence.

Evidence: [Locust summary](raw/locust-results.json), [run 1 CSV](raw/locust-v2e-run-1_stats.csv), [run 2 CSV](raw/locust-v2e-run-2_stats.csv), [run 3 CSV](raw/locust-v2e-run-3_stats.csv), and the corresponding HTML reports in `raw/`.
