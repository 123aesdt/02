# Redis Reliability Acceptance

Date: 2026-08-26. Runtime: real Redis 7.4 with AOF and real Docker workers.

| Scenario | Evidence | Result |
|---|---|---|
| Worker kill / Pending / XAUTOCLAIM | Five formal recovery runs | PASS |
| Retry | Delivery counts 1→2→3 | PASS |
| DLQ | Delivery 3 moved to DLQ; identity preserved; original ACKed | PASS |
| Redis restart / AOF | Marker stream entry survived container restart | PASS |
| Duplicate delivery | Duplicate stream entry delivered and ACKed; counts stayed 1/1 | PASS |
| Same idempotency concurrency | HTTP 202/202, same task ID, duplicate flags false/true | PASS |

Final task-stream pending: 0. Message loss: 0. Duplicate Dispatch: 0. Duplicate Audit: 0. Raw evidence: `raw/redis-reliability-results.json`.
