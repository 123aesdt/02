# Phase 5B Final Acceptance Implementation Plan

> **For agentic workers:** Execute inline in the current workspace. Do not commit, change Git author, or discard existing user changes. Every production behavior change uses a witnessed RED → GREEN cycle.

**Goal:** Produce auditable evidence for the Phase 5B recovery, reliability, fallback, concurrency, memory, load, regression, and Git acceptance matrix without adding business features.

**Architecture:** Keep the single Docker runtime. Make recovery latency a bounded configuration budget whose orphan-lock TTL is shorter than pending eligibility and whose read cadence plus retry delay leaves margin below five seconds. Put acceptance orchestration and metric calculation in focused scripts, store raw JSON/CSV/HTML under `docs/verification/raw`, and derive Markdown summaries only from those raw artifacts.

**Tech Stack:** Python 3.12, pytest, asyncio, Redis Streams, SQLAlchemy/MySQL 8.4, Qdrant, Locust, PowerShell, Docker Compose.

**Spec:** User-provided `PHASE 5B — FINAL ACCEPTANCE & PERFORMANCE` directive dated 2026-08-26.

## Global Constraints

- Use the existing eight-service `docker-compose.yml`; do not create a second runtime.
- Preserve blocking Redis reads, positive pending idle, retry delay, execution lock, and idempotency ledger.
- Every one of five recovery runs must be `<=5.0s`, with one Dispatch, one Audit, zero pending, and zero message loss.
- Run three Locust stable windows against `http://localhost:8001`; HTTP acceptance excludes Graph terminal latency.
- A missing real Embedding credential yields the prescribed PARTIAL status; it does not permit a fake formal Top-1 claim.
- Save raw artifacts and do not commit.

---

### Task 1: Recovery budget and regression protection

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose.yml`
- Modify: `backend/tests/unit/test_settings.py`

**Interfaces:**
- Consumes current `worker_block_ms`, `worker_pending_min_idle_ms`, `worker_retry_base_delay_ms`, and `worker_idempotency_lock_ttl_ms`.
- Produces a docker-dev configuration in which pending idle remains greater than the orphan lock TTL and the configured recovery budget is below five seconds.

- [ ] Add a settings test proving the accepted bounded values and a test rejecting an unsafe pending-idle/lock relationship.
- [ ] Run the focused test and confirm the existing 31-second Compose configuration fails the acceptance assertion.
- [ ] Set the smallest measured values that preserve blocking reads and non-zero retry delay.
- [ ] Run settings, lock, pending recovery, retry, and idempotency tests.

### Task 2: Formal worker recovery runner

**Files:**
- Modify: `scripts/docker_worker_recovery_e2e.py`
- Create: `backend/tests/unit/test_acceptance_metrics.py`
- Create: `backend/app/acceptance/metrics.py`
- Create: `docs/verification/raw/worker-recovery-results.json`
- Create: `docs/verification/worker-recovery-results.md`

**Interfaces:**
- `summarize_recovery(runs: Sequence[RecoveryRun]) -> RecoverySummary` computes max latency and invariant failures from literal run records.
- Runner records T1 kill, pending eligibility, XAUTOCLAIM ownership transfer, terminal persistence, ACK, counts, pending, and loss for five independent runs.

- [ ] Write metric tests with hand-derived min/average/p95/max and invariant failures; verify RED.
- [ ] Implement only the calculation types/functions; verify GREEN.
- [ ] Extend the real runner with `--runs 5`, JSON output, bounded condition polling, cleanup, and per-run facts.
- [ ] Rebuild workers and execute five real kills; require every run `<=5.0s`.

### Task 3: Redis reliability, fallback, conflict, and business acceptance

**Files:**
- Create: `scripts/docker_acceptance_scenarios.py`
- Create: `docs/verification/raw/redis-reliability-results.json`
- Create: `docs/verification/raw/fallback-results.json`
- Create: `docs/verification/raw/concurrency-results.json`
- Create: `docs/verification/raw/business-errors-results.json`
- Create: corresponding Markdown summaries under `docs/verification/`

**Interfaces:**
- Scenario subcommands return JSON with explicit numerator, denominator, unit, and pass/fail fields.

- [ ] Add tests for percentile/rate aggregation before implementation.
- [ ] Run retry/DLQ, Redis AOF restart, duplicate delivery, and same-key concurrency using real Redis/MySQL.
- [ ] Run ten real Docker-worker environment timeout/fallback cases; save all elapsed milliseconds and require max `<=1000`.
- [ ] Run twenty two-session MySQL conflicts; require twenty `StaleDataError` interceptions and no silent overwrite.
- [ ] Run the defined normal/fallback/manual-review/duplicate/recovery/conflict workload and require zero unexpected business errors.

### Task 4: Memory benchmark and adoption suite

**Files:**
- Create: `benchmarks/memory/memories.json`
- Create: `benchmarks/memory/queries.json`
- Create: `benchmarks/memory/adoption_cases.json`
- Create: `scripts/run_memory_benchmark.py`
- Create: `docs/verification/raw/memory-benchmark-results.json`
- Create: `docs/verification/memory-benchmark-results.md`
- Test: `backend/tests/unit/test_memory_benchmark.py`

**Interfaces:**
- Dataset contains at least 50 diverse queries with literal `expected_top1_memory_id` values and multiple memory records.
- Runner always executes EmbeddingProvider → real Qdrant collection → Top-K; it never performs ID lookup or manual sorting.

- [ ] Write dataset-schema, diversity, metric, and adoption positive/negative tests; verify RED.
- [ ] Implement loader and metric calculation; verify GREEN.
- [ ] Detect provider configuration without printing secrets.
- [ ] If configured, load a disposable Qdrant benchmark collection and compute formal Top-1/Top-3; otherwise emit `REAL EMBEDDING BENCHMARK BLOCKED BY CREDENTIAL` with dataset/runner/Qdrant readiness evidence.
- [ ] Execute valid adoption cases and incompatible negative cases through the real routing service; require 100% valid adoption and 0% invalid adoption.

### Task 5: Locust workload and three stable runs

**Files:**
- Create: `loadtests/locustfile.py`
- Create: `loadtests/README.md`
- Create: `docs/verification/raw/locust-run-{1,2,3}.csv`
- Create: `docs/verification/raw/locust-run-{1,2,3}.html`
- Create: `docs/verification/locust-results.md`
- Test: `backend/tests/unit/test_loadtest_workload.py`

**Interfaces:**
- Health/status/result traffic uses seeded real task IDs; POST uses unique idempotency keys and controlled test identities.
- Stable-window calculation reports aggregate QPS, P50, P95, P99, error rate, CPU, and memory separately from Agent terminal latency.

- [ ] Write an import-level test that executes workload request builders and asserts unique valid POST payloads; verify RED.
- [ ] Implement the workload and install a pinned compatible Locust version.
- [ ] Warm up, then step through 50/100/200 users to find the stable operating point.
- [ ] Run three 60-second headless acceptance windows; save CSV/HTML and Docker resource snapshots.
- [ ] If any run misses QPS/P95/error targets, diagnose one bottleneck at a time, add a failing regression test for code changes, optimize, and rerun all three.

### Task 6: Acceptance orchestrator and documentation

**Files:**
- Create: `scripts/run-acceptance.ps1`
- Test: `backend/tests/unit/test_acceptance_script.py`
- Update: `README.md`

**Interfaces:**
- The PowerShell orchestrator executes readiness → reliability → fallback → conflict → memory credential gate → Locust → regression, preserves the first non-zero exit, and never prints secrets.

- [ ] Write a behavioral test with controlled child scripts showing first-failure propagation; verify RED.
- [ ] Implement the minimal orchestrator; verify GREEN.
- [ ] Update README with commands, metric definitions, artifact locations, and the real-credential caveat.

### Task 7: Fresh final verification

- [ ] Recompute every headline metric from raw records and reconcile denominators, units, duplicate counts, and percentile method.
- [ ] Run `ruff check backend`, backend pytest (`>=224`), frontend lint/tests (`>=33`), frontend build, and `scripts/check.ps1`.
- [ ] Run Docker config/build/up/health/log checks and ensure Redis pending is zero.
- [ ] Run `git diff --check`, `git diff --cached --check`, and `git status --short`.
- [ ] Issue COMPLETE only if every hard metric passes; otherwise issue the credential-only PARTIAL status if and only if that is the sole missing item.
