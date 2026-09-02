# V2-E Reliability Acceptance

Status: **PASS**

- Worker recovery: 5/5, min 4.678s, avg 4.770s, p95/max 4.824s; duplicate dispatch 0, duplicate audit 0, message loss 0, Pending=0.
- Redis Streams: same-idempotency concurrency, duplicate delivery, bounded retry/DLQ, XAUTOCLAIM recovery, restart and AOF persistence passed.
- Static-route fallback: 20/20 under one second; p95 802.176ms, max 802.208ms.
- MySQL optimistic concurrency: 20/20 StaleDataError intercepted; silent overwrite 0.
- Independent MySQL, Redis, Neo4j, Qdrant restarts and a full Compose down/up without `-v` preserved required state.
- Business workload unexpected errors: 0.

Evidence: [worker recovery](raw/worker-recovery.json), [Redis](raw/redis-reliability.json), [fallback](raw/fallback.json), [dispatch concurrency](raw/dispatch-concurrency.json), [restart persistence](raw/restart-persistence.json), [business acceptance](raw/business-acceptance.json).
