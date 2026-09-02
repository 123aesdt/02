# V2-D1 Runtime Override Verification

Date: 2026-08-27. Scope is V2-D1 only.

## Result

V2-D1 passed its unit, component, real-server, Docker, recovery, frontend, and load gates. MySQL canonical promotion is the mutation linearization point. Redis override checkpoints remain noncanonical until that promotion; Worker resume uses the exact MySQL checkpoint ID and a single-winner boundary CAS.

## Real override evidence

The real-server harness used MySQL 8.4 and Redis 8.2.9 with the official `AsyncRedisSaver`:

| Gate | Result |
| --- | --- |
| Legal `NORMAL -> BROKEN` overrides | 20/20 APPLIED |
| Capacity observations | 20/20 read BROKEN |
| Stale expected versions | 20/20 blocked; silent mutations 0 |
| Worker/Override boundary races | 20 iterations; invariant violations 0 |
| Thread lock TTL | 8000 ms |
| Required TTL from observed max + 2000 ms | 2181.219 ms |

Observed override latency in milliseconds:

| Phase | Min | Average | P95 | P99/max |
| --- | ---: | ---: | ---: | ---: |
| Authorization | 2.560 | 3.112 | 3.725 | 4.155 |
| Lock | 0.611 | 0.817 | 1.012 | 1.114 |
| Exact checkpoint read | 2.157 | 2.531 | 2.846 | 2.947 |
| State update | 11.525 | 12.816 | 14.113 | 14.236 |
| MySQL promotion | 16.929 | 22.635 | 22.324 | 81.563 |
| Total | 109.190 | 120.044 | 127.462 | 181.219 |

Raw evidence: `docs/verification/raw/v2-d1-runtime-override.json`.

## Regression evidence

- Backend: 480 passed, 3 skipped; the three environment-gated cases also passed when explicitly run against the live Docker services (two Redis-checkpointer tests and one four-store shared-memory race test).
- Frontend: lint PASS, 40 tests PASS, production build PASS.
- Docker: nine services healthy; Redis/MySQL/Qdrant/Neo4j, WebSocket, shared-memory recovery, official checkpoint benchmark, graph topology, and V1 business E2E PASS; Pending=0.
- Worker crash recovery: 4.407 / 4.387 / 4.396 seconds, all below 5 seconds, exact observed checkpoint resumed, one dispatch and one audit per run.
- V1 business result: `memory-rain-li -> national-102 -> REROUTE -> APPROVED`.
- Real public API override: `C4/V4 -> C5/V5`, APPLIED, event PUBLISHED; the resumed task became REVIEW_REQUIRED with no dispatch because Capacity consumed the promoted BROKEN status; Pending=0.
- Locust, three 60-second runs: minimum QPS 280.519, maximum P95 270 ms, maximum error rate 0%; PASS.
- The unchanged formal embedding evidence remains 49/50 Top-1 (98%). The retrieval and routing paths passed backend and Docker regression without changing the benchmark dataset or memory algorithms.

## Failure and security semantics

- Authorization identity is server-owned and requires `runtime:override`.
- Only `Vehicle.status` at Environment -> Capacity is mutable, and only from NORMAL to BROKEN, UNAVAILABLE, or MAINTENANCE.
- Values are never written through raw Redis keys; mutation uses official `aupdate_state`.
- Result validation enforces exact thread/namespace, direct ancestry, bounded size, JSON serialization, unchanged completed-node count, and a one-field diff.
- Promotion and the durable APPLIED audit metadata commit in one MySQL transaction.
- Event delivery failure leaves APPLIED unchanged and cannot rerun state mutation.
- PARTIAL reconciliation reads only recorded source/result checkpoint IDs and never scans Redis latest.
