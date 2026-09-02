# Worker Recovery Acceptance

Date: 2026-08-26. Runtime: real Docker workers and Redis Streams.

## Root cause

The measured pre-fix recovery was 32.871 s (29.530 s waiting for ACK). The runtime was not using a 30-second `XREADGROUP` block; its read block was 1 second. The dominant delay was the configured 31,000 ms pending eligibility threshold, chosen to exceed a 30,000 ms execution-lock TTL. Recovery therefore could not begin inside the 5-second SLA.

The accepted bounded budget is now: lock TTL 2,000 ms; pending minimum idle 2,500 ms; blocking read 250 ms; retry base 100 ms. Blocking reads, nonzero retry delay, execution locking, and pending eligibility remain enabled. Configuration validation rejects a Docker recovery budget at or above 5,000 ms.

## Formal results

| Run | T1→T2 s | T2→T3 s | T3→T4 s | T4→T6 s | Total s | Dispatch | Audit | Pending | Lost | Status |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 2.305 | 0.187 | 0.0009 | 2.114 | 4.607 | 1 | 1 | 0 | 0 | PASS |
| 2 | 2.317 | 0.103 | 0.0009 | 2.103 | 4.523 | 1 | 1 | 0 | 0 | PASS |
| 3 | 2.318 | 0.082 | 0.0010 | 2.095 | 4.496 | 1 | 1 | 0 | 0 | PASS |
| 4 | 2.309 | 0.198 | 0.0008 | 2.110 | 4.618 | 1 | 1 | 0 | 0 | PASS |
| 5 | 2.276 | 0.159 | 0.0011 | 2.137 | 4.573 | 1 | 1 | 0 | 0 | PASS |

Min/avg/P95/max: 4.496 / 4.563 / 4.618 / 4.618 s. Every run passed the 5.0-second ceiling. Raw evidence: `raw/worker-recovery-results.json`.
