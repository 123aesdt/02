# Phase 5A Real Docker Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify and, only where evidence requires it, repair the single CountyFlow Docker runtime so the browser-to-Redis-to-two-workers-to-seven-agent-to-MySQL/Qdrant-to-WebSocket path is demonstrably real and durable.

**Architecture:** Preserve `docker-compose.yml` as the only runtime definition. MySQL 8 is the system of record, Redis Streams provides queue/event/lock/DLQ behavior, Qdrant Server stores entity-resolution memory, a one-shot migration service owns Alembic and idempotent seed work, two worker containers execute the graph, and the Nginx frontend uses the host-visible FastAPI URL.

**Tech Stack:** Docker Desktop 29.7.2, Docker Compose v5.4.0, MySQL 8.4, Redis 7.4, Qdrant 1.13.2, FastAPI, SQLAlchemy/Alembic, LangGraph, React/Vite/Nginx, pytest, Vitest, Playwright.

**Spec:** User-provided `PHASE 5A — REAL DOCKER RUNTIME & FULL E2E` instruction (2026-08-26), plus `docs/design.md` and `AGENTS.md`.

## Global Constraints

- Keep exactly one Compose architecture with `mysql`, `redis`, `qdrant`, `migration`, `backend`, `worker-1`, `worker-2`, and `frontend`.
- Docker runtime uses `RUNTIME_PROFILE=docker-dev`, real MySQL/Redis/Qdrant, and only the explicitly allowed deterministic development providers.
- Alembic runs once in `migration`; backend and workers never call `Base.metadata.create_all()` or migrate concurrently.
- Use behavior-first failing tests before production-code changes; configuration-only fixes are validated by `docker compose config` and the real runtime.
- Never hard-code credentials, expose secrets, use wildcard CORS, add a second Compose file, commit automatically, or modify Git author.
- Do not remove volumes during restart verification and never claim exactly-once delivery.

---

### Task 1: Validate the existing Compose contract and launcher portability

**Files:**
- Modify if required: `docker-compose.yml`
- Modify if required: `scripts/start-full.ps1`
- Test: `backend/tests/unit/test_docker_runtime_files.py`
- Test: `backend/tests/unit/test_dev_launcher_scripts.py`

**Interfaces:**
- Consumes: `.docker.env` keys `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`.
- Produces: one valid eight-service Compose model and a launcher that discovers either PATH Docker or the installed user/system Docker CLI without permanent PATH mutation.

- [ ] Run `docker compose --env-file .docker.env config` with the discovered Docker executable and record the first concrete failure, if any.
- [ ] If launcher discovery is missing, add a failing unit test requiring PATH, standard system install, and current-user Docker Desktop install lookup while rejecting hard-coded project paths.
- [ ] Run the targeted pytest test and confirm it fails for the missing behavior.
- [ ] Implement the smallest reusable PowerShell Docker-command resolution and use it for `info` and Compose startup.
- [ ] Re-run targeted tests and `docker compose config`; require exit code 0 and exactly eight service names.

### Task 2: Build and reach a healthy real infrastructure runtime

**Files:**
- Modify if required: `docker-compose.yml`
- Modify if required: `backend/Dockerfile`
- Modify if required: `frontend/Dockerfile`
- Modify if required: `infra/qdrant.Dockerfile`
- Modify if required: `backend/app/seed.py`
- Test: `backend/tests/unit/test_docker_runtime_files.py`

**Interfaces:**
- Consumes: Compose health conditions and the existing Alembic head.
- Produces: MySQL/Redis/Qdrant/backend/frontend health, migration exit 0, two live workers, and an idempotently seeded `entity_resolution_memory` collection.

- [ ] Run `docker compose build`, then `docker compose up -d`, and collect `ps` plus bounded logs.
- [ ] For each failure, trace the failing boundary from container environment to dependency health before changing code.
- [ ] Add the narrowest failing static or behavior test for any source/config defect that can be automated.
- [ ] Apply one minimal fix per confirmed root cause and rerun its targeted test.
- [ ] Verify migration is at repository head and query MySQL for `orders`, `anomalies`, `dispatch_tasks`, `dispatches`, and `audit_records`.
- [ ] Verify Redis `PING`, AOF configuration, Qdrant `/collections`, and exactly one logical `memory-rain-li` seed after repeated migration/seed execution.

### Task 3: Prove the core async task, seven-agent, persistence, ACK, and WebSocket paths

**Files:**
- Modify if required: `scripts/test-docker.ps1`
- Modify if required: `scripts/docker_ws_e2e.py`
- Modify if required: backend/runtime files identified by evidence
- Test: targeted backend tests matching each changed runtime component

**Interfaces:**
- Consumes: seeded order/anomaly IDs and host endpoints `http://localhost:5173`, `http://localhost:8001`, `ws://localhost:8001`.
- Produces: a recorded `task_id`, route `national-102`, audit `APPROVED`, one dispatch, one audit, `XPENDING=0`, and the complete real event sequence.

- [ ] Submit the core rain/slippery task through the API and require HTTP 202.
- [ ] Capture Redis stream/group evidence, worker identity/log evidence, Qdrant recall evidence, and final MySQL rows for that exact `task_id`.
- [ ] Extend the E2E checker first so it fails unless snapshot, accepted, worker, all seven agents, terminal, HTTP refetch, replay, and `last_event_id` reconnect are demonstrated.
- [ ] Make the minimal source fix for each reproducible failure, keeping event contract names aligned with backend models.
- [ ] Re-run the E2E checker and verify ACK plus pending count zero.

### Task 4: Prove browser API mode and reconnect behavior

**Files:**
- Modify if required: `frontend/src/services/task-event-client.ts`
- Modify if required: `frontend/src/hooks/use-task-events.ts`
- Modify if required: `frontend/src/pages/api-dispatch-detail-page.tsx`
- Test: `frontend/tests/task-event-client.test.ts`
- Test: temporary Playwright evidence outside the repository

**Interfaces:**
- Consumes: the production Nginx frontend and real backend HTTP/WebSocket APIs.
- Produces: browser-origin POST 202, visible agent events/result, close/reopen replay, forced disconnect/reconnect recovery, and no relevant console or CORS errors.

- [ ] Use repo Playwright because the Browser plugin is not available in this session; target `http://localhost:5173`.
- [ ] Exercise `/dispatch`, click `发起 AI 调度`, record navigation/task ID, and verify the terminal route/audit UI.
- [ ] Reload and reopen the same task to prove snapshot plus replay.
- [ ] Interrupt the socket during an in-flight task, verify execution continues, and assert reconnect/refetch restores the terminal state.
- [ ] If a frontend defect appears, add a failing Vitest behavior test, verify red, implement the minimal fix, then verify green and rerun Playwright.

### Task 5: Prove real concurrency, DLQ, worker recovery, and persistence

**Files:**
- Create if required: `scripts/docker_reliability_e2e.py`
- Modify if required: `scripts/test-docker.ps1`
- Modify if required: backend worker/queue/idempotency files identified by evidence
- Test: targeted backend tests matching each changed behavior

**Interfaces:**
- Consumes: two real worker containers, real Redis consumer group, and two independent MySQL SQLAlchemy sessions.
- Produces: `StaleDataError` mapped to domain conflict, a preserved-identity DLQ record, `XAUTOCLAIM` recovery timing, and effectively-once dispatch/audit counts.

- [ ] Run a real-MySQL two-session optimistic-lock scenario and record the stale second commit without overwrite.
- [ ] Run a controlled real-Redis retry-to-DLQ scenario and verify original message/task identity plus original ACK.
- [ ] Create an in-flight unacked message, stop `worker-1`, and measure `worker-2` recovery through pending inspection and `XAUTOCLAIM` evidence.
- [ ] Query MySQL after recovery and require dispatch count 1 and audit count 1.
- [ ] Run `docker compose down` without `-v`, start again, and verify MySQL data, Qdrant memory, non-duplicated seed, and Redis persistence.

### Task 6: Verify launcher and all regression gates

**Files:**
- Modify if required: `scripts/start-full.ps1`
- Modify if required: `scripts/test-docker.ps1`
- Review only: all Phase 5A diffs

**Interfaces:**
- Consumes: the completed real runtime and repository quality scripts.
- Produces: launcher evidence, full regression counts, clean diff checks, and the final verified/not-verified matrix.

- [ ] Run `scripts/start-full.ps1` without allowing it to persistently alter PATH; verify Compose startup, readiness wait, and browser launch behavior.
- [ ] Run backend Ruff and all backend tests; require at least 221 passes.
- [ ] Run frontend lint, all frontend tests, and production build; require at least 31 passes.
- [ ] Run `scripts/check.ps1` and require `[OK] All quality gates passed.` with exit code 0.
- [ ] Run `git diff --check`, `git diff --cached --check`, and `git status --short` without committing or changing author identity.
- [ ] Re-read every Phase 5A completion checkbox and report only claims supported by fresh command/browser/database evidence.
