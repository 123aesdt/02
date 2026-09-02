# V2-E Final Acceptance

Overall status: **COMPLETE**

All previously verified V2-E acceptance evidence remains unchanged. The fresh local real-embedding regression passed the locked threshold and removes the final V2-E blocker.

Fresh Real Embedding Regression: **VERIFIED** — [v2-e-real-embedding-regression.json](raw/v2-e-real-embedding-regression.json), generated locally by the user at `2026-08-27T21:16:56.969892+08:00`. This is current V2-E evidence, not the historical Phase 5B result.

## Fresh vector result

| Field | Fresh result |
|---|---:|
| Provider host | api.siliconflow.cn |
| Model | Qwen/Qwen3-Embedding-4B |
| Dimension | 2560 |
| Dataset | 50 queries / 10 memories |
| Top-1 | 49/50 (98.00%) |
| Top-3 | 50/50 (100.00%) |
| Failed queries | query-045: expected `memory-cold-zheng`, actual `memory-battery-sun`; expected memory was in Top-3 |
| Threshold | >=46/50 Top-1 |
| Result | VERIFIED (`passed=true`) |

## Final acceptance matrix

| Metric | Target | Measured | Status |
|---|---:|---:|---|
| 15-round black box | PASS | 15/15, one task/thread | PASS |
| Round 12 override | APPLIED, version +1 | APPLIED, 4→5 | PASS |
| Round 13 Capacity | reads BROKEN | BROKEN / unavailable | PASS |
| Round 14 Routing | excludes vehicle | MANUAL_REVIEW, no vehicle | PASS |
| Round 15 canonical | no stale reuse | BROKEN retained | PASS |
| Vector Memory Top-1 | >=92% | 49/50 (98.00%) | VERIFIED |
| Vector Memory Top-3 | regression | 50/50 (100.00%) | VERIFIED |
| Graph extraction | exact | entities 3/3, relations 3/3 | PASS |
| Graph recall | 20 queries | facts 20/20, paths 20/20 | PASS |
| Graph P95 | <150ms | 10.354ms | PASS |
| Shared Memory lost update | 0 | 0/20 | PASS |
| Staged projection leaks | 0 | Qdrant 0, Neo4j 0 | PASS |
| Duplicate projections | 0 | points 0, relations 0 | PASS |
| Override success | 100% | 50/50 | PASS |
| Downstream stale reads | 0 | 0/50 | PASS |
| Concurrent override | one winner | 20/20 | PASS |
| Checkpoint exact/N+1 resume | PASS | 5/5 | PASS |
| Dispatch conflicts | intercepted | 20/20 | PASS |
| Duplicate dispatch | 0 | 0 | PASS |
| Duplicate audit | 0 | 0 | PASS |
| Fallback | <=1s | p95 802.176ms | PASS |
| Business errors | 0 | 0 | PASS |
| Locust QPS | >=200 | min 400.071 | PASS |
| Locust P95 | <300ms | max 200ms | PASS |
| Locust error rate | <0.1% | max 0% | PASS |
| Worker recovery | every run <=5s | 5/5, max 4.824s | PASS |
| Redis message loss | 0 | 0 | PASS |
| Restart persistence | PASS | all four stores + full restart | PASS |
| Browser scenarios | PASS | 7/7 | PASS |
| Screenshots | >=8 real API | 10 | PASS |
| Backend regression (V2-E phase snapshot) | no regression | 512 passed, 3 integration gates skipped in default run | PASS |
| Real integration gates | PASS | Redis 2/2; Shared Memory 1/1 | PASS |
| Frontend regression (V2-E phase snapshot) | PASS | 13 files / 64 tests; lint/build pass | PASS |
| `scripts/check.ps1` | PASS | PASS | PASS |
| Docker runtime | 9 services | 8 healthy running + migration exit 0 | PASS |
| Redis Pending | 0 | 0 | PASS |
| Secret scan | 0 | 0 | PASS |
| Git whitespace checks | PASS | worktree + cached exit 0 | PASS |

## Evidence inventory

- Fresh Vector Memory: [v2-e-real-embedding-regression.json](raw/v2-e-real-embedding-regression.json).
- 15-round black box: [15-round-blackbox.json](raw/15-round-blackbox.json).
- Graph Memory and latency: [graph-memory.json](raw/graph-memory.json).
- Shared Memory and projection visibility: [shared-memory.json](raw/shared-memory.json).
- Runtime Override and downstream visibility: [runtime-override.json](raw/runtime-override.json).
- Checkpoint: [checkpoint.json](raw/checkpoint.json) and [checkpoint-recovery.json](raw/checkpoint-recovery.json).
- Worker recovery and Redis message loss: [worker-recovery.json](raw/worker-recovery.json) and [redis-reliability.json](raw/redis-reliability.json).
- Duplicate dispatch/audit and concurrency: [dispatch-concurrency.json](raw/dispatch-concurrency.json) and [15-round-blackbox.json](raw/15-round-blackbox.json).
- Fallback: [fallback.json](raw/fallback.json).
- QPS, P95, and error rate: [locust-results.json](raw/locust-results.json).
- Business errors: [business-acceptance.json](raw/business-acceptance.json).
- Restart persistence: [restart-persistence.json](raw/restart-persistence.json).
- Ten real-browser screenshots are under [screenshots](screenshots/).
- Reviews: [race audit](race-condition-audit.md), [AI review](../../ai-review.md).
- Final gate snapshot: [final-gates.json](raw/final-gates.json).

The only refreshed acceptance item is the local real-embedding result. No business source changed after the prior V2-E evidence run, so the completed heavy acceptance artifacts above were not rerun.

The repository-wide freeze baseline is newer than these two V2-E phase-snapshot test counts: V2-F and the final freeze gate record 525 backend tests and 77 frontend tests. The V2-E raw artifacts remain unchanged historical evidence.

Final verdict: **V2-E COMPLETE** — the fresh local real-embedding regression passed, and all previously verified V2-E evidence remains valid.
