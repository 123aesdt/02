# Locust Performance Acceptance

Date: 2026-08-27. Locust 2.46.4 targeted the real nine-service Docker runtime with MySQL 8.4, Redis 8 AOF, Qdrant Server, Neo4j Community, and two workers.

Configuration: 50 users, spawn rate 25 users/s, 60 seconds per formal run, 10–50 ms user wait. Task weights were GET health 50, GET status 30, GET result 19, POST submission 1. Every POST used a unique idempotency key. HTTP acceptance/query latency was measured separately from background Graph terminal latency.

| Run | Requests | QPS | P50 | P95 | P99 | Error rate | Status |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 18,661 | 314.121 | 110 ms | 240 ms | 290 ms | 0.0000% | PASS |
| 2 | 18,898 | 318.940 | 110 ms | 230 ms | 300 ms | 0.0000% | PASS |
| 3 | 19,025 | 320.935 | 110 ms | 240 ms | 310 ms | 0.0000% | PASS |

Worst formal QPS/P95/error rate: 314.121 / 240 ms / 0.0000%. The load profile exercises the existing dispatch HTTP path; background graph completion latency is excluded from the HTTP percentile. The separate resource snapshot remains in `raw/locust-resource-sample.json`.

Raw evidence includes `raw/locust-results.json`, three stats/history/failure/exception CSV sets, and three Locust HTML reports.
