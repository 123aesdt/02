# V2-D2 Runtime Intervention Workbench Verification

Date: 2026-08-27. Scope is V2-D2 only.

## Result

V2-D2 adds the Runtime Intervention Workbench to the existing dispatch detail page while preserving the V2-D1 mutation core. Backend eligibility and safe read models are authoritative; the frontend submits only the allowlisted `Vehicle.status` transition and frozen checkpoint preconditions. Actor identity, role, and permissions continue to come only from the server authorization context.

## TDD and regression evidence

Behavior-level RED runs were observed before implementation for the missing query models/service, authenticated read endpoints, safe event fields, Capacity projection, frontend DTO/client, orchestration hooks, dialog behavior, and browser harness. The smallest implementations were then exercised through targeted GREEN runs before full regression.

| Gate | Measured result |
| --- | --- |
| Backend Ruff | PASS |
| Backend pytest | 506 passed, 3 environment-gated skipped, 1 dependency deprecation warning |
| Frontend lint | PASS |
| Frontend Vitest | 13 files, 64 tests passed |
| Frontend production build | PASS; 380.57 kB JS, 116.10 kB gzip |
| `scripts/check.ps1` | PASS |

The frontend suite includes all 17 required component/hook tests and the four additional safety tests for immutable stale snapshots, idempotency-key reuse, HTTP-owned APPLIED state, and duplicate-event suppression.

## Truth and safety boundaries

- The intervention context GET combines the canonical MySQL thread pointer, exact Redis checkpoint, and server authorization result. It returns `ELIGIBLE`, `NOT_STABLE`, `TERMINAL`, `NO_PERMISSION`, `WRONG_BOUNDARY`, or `BUSY`; the browser does not reconstruct policy.
- POST response plus runtime-thread and override detail/history GETs are business truth. WebSocket events are notifications that trigger coalesced refresh and never downgrade an HTTP `APPLIED` result.
- Opening the dialog freezes version, checkpoint, next node, entity, field, old value, and new value. A later canonical change makes the dialog stale and disables submission; it never rebases.
- The first confirm creates one idempotency key. Retrying a transport/503 failure reuses that key; a newly opened intervention gets a new key.
- `PARTIAL` never automatically re-POSTs. It performs only three GET observations at 2, 6, and 14 elapsed seconds, then stops.
- History and events expose bounded safe summaries only. They exclude idempotency fingerprints, auth material, checkpoint payloads, and internal stacks.
- API mode fails visibly when the backend is unavailable and never falls back to mock data. Mock mode uses an isolated presentational flow and never calls the real override API.

## Real browser and Docker evidence

Playwright 1.62.1 ran against the API-mode frontend and the real Docker runtime. The combined JSON report contains five expected tests, zero unexpected tests, and zero skipped tests:

1. Success: `NORMAL -> BROKEN` returned APPLIED, incremented runtime version exactly once, changed the canonical checkpoint, Capacity read `BROKEN` with `vehicle_available=false`, history showed APPLIED, and the task ended `REVIEW_REQUIRED`.
2. Stale: a canonical runtime change after dialog open produced STALE and disabled Confirm without rebasing the captured version.
3. Concurrent: two independent browser contexts produced one APPLIED winner and one BUSY/CONFLICT loser; the runtime version increased only once.
4. Forbidden: the action was unavailable in the UI and direct POST returned 403.
5. Terminal: the action was disabled and direct POST returned `THREAD_TERMINAL`.

The final success trace recorded 30 bounded Runtime GETs across the complete eventful task lifecycle. During an explicit 1.1-second stable observation window the count remained 5 to 5, proving there is no 200 ms or other periodic Runtime poll. Refreshes are driven by HTTP submission and deduplicated WebSocket lifecycle notifications.

Raw browser evidence: `docs/verification/raw/v2-d2-browser-e2e.json`. Separate trusted/forbidden reports are retained beside it.

Real screenshots:

- `docs/assets/frontend-demo/runtime-intervention-eligible.png`
- `docs/assets/frontend-demo/runtime-intervention-confirm.png`
- `docs/assets/frontend-demo/runtime-intervention-applied.png`
- `docs/assets/frontend-demo/runtime-intervention-capacity-broken.png`
- `docs/assets/frontend-demo/runtime-intervention-review-required.png`

Docker verification reported nine configured services and eight long-running services, with the migration service completing as a one-shot job. MySQL, Redis 8, Qdrant, Neo4j Community, backend, frontend, worker-1, and worker-2 were running; Redis Stream Pending was 0.

## V1 and recovery regression

The no-override real Docker scenario remained `memory-rain-li -> national-102 -> REROUTE -> APPROVED`, with Pending 0. The D2 override scenario intentionally ended `REVIEW_REQUIRED`; no routing rule was changed to make the demonstration pass.

Five real worker-kill recovery trials completed in 4.800, 4.856, 4.827, 4.945, and 4.984 seconds. Maximum and P95 were 4.984 seconds; every run persisted exactly one dispatch and audit, lost no message, and ended with Pending 0. Raw evidence: `docs/verification/raw/worker-recovery-results.json`.

The checkpoint recovery portion of the Docker gate also passed three trials at 4.521, 4.431, and 4.393 seconds with exact canonical checkpoint resume and no duplicate nodes, dispatch, audit, or memory mutation. Raw evidence: `docs/verification/raw/v2-c-checkpoint-recovery.json`.

## Performance

Three fresh 60-second Locust runs used 50 users at 25 users/second:

| Run | Requests | QPS | P95 | Error rate |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 18,661 | 314.121 | 240 ms | 0.0000% |
| 2 | 18,898 | 318.940 | 230 ms | 0.0000% |
| 3 | 19,025 | 320.935 | 240 ms | 0.0000% |

All runs passed QPS >= 200, P95 < 300 ms, and error rate < 0.1%. Raw JSON, CSV, and HTML evidence is under `docs/verification/raw/`.

## Deferred scope

V2-D2 does not add Pause, Resume, rollback, goto, skip, rerun, arbitrary JSON/state mutation, reverse vehicle transitions, shared-memory mutation, or any V2-E capability. `backend/app/runtime_overrides/service.py`, checkpoint promotion, thread locking, boundary CAS, idempotency, reconciliation, and authorization semantics remain frozen.
