# CountyFlow AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an executable, testable, Docker-deployable CountyFlow AI modular-monolith system with a React operations console and real asynchronous dispatch infrastructure.

**Architecture:** FastAPI admits and queries work; Redis Streams transfers tasks to a separate worker; a typed LangGraph orchestrates seven port-dependent agents; MySQL persists business truth and Qdrant recalls entity-resolution vectors. React receives query data and ordered task events over WebSocket.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, LangGraph, Redis, MySQL 8, Qdrant, httpx, pytest, ruff, React, TypeScript, Vite, TanStack Query, Tailwind CSS, Recharts, Lucide, Docker Compose, Locust.

**Spec:** `docs/superpowers/specs/2026-08-21-countyflow-design.md`

## Global Constraints

- Production graph execution is worker-only; API code never executes the complete graph synchronously.
- `Dispatch.version` uses SQLAlchemy `version_id_col`; conflicts are HTTP 409.
- Redis Streams use group ACK, durable idempotency, recovery, bounded retry, and cancellation-safe shutdown.
- Qdrant recall must perform embedding-based similarity search.
- Production model calls use only the configured OpenAI-Compatible adapter; tests use fake adapters without a network.
- Weather/road and model clients use explicit async timeouts and safe error normalization; weather/road fallback must complete within one second.
- No keys in source, commits, logs, test output, screenshots, or client bundles.

---

### Task 1: Bootstrap executable dependency and configuration boundary

**Files:** Create `backend/pyproject.toml`, `backend/app/core/settings.py`, `backend/app/core/errors.py`, `backend/app/main.py`, `.env.example`; modify `Makefile`.

**Interfaces:** Produces `Settings`, `AppError`, and an application factory consumed by all later tasks.

- [ ] Write a failing settings test that sets separate LLM and embedding environment variables and asserts models/base URLs differ while keys never appear in `repr`.
- [ ] Run `pytest backend/tests/test_settings.py -v`; expect failure because settings are absent.
- [ ] Implement Pydantic settings with environment-only secrets, application factory, dependency tooling, and Makefile commands that execute ruff/pytest/frontend checks when code exists.
- [ ] Rerun the targeted test and `ruff check backend`; expect both to pass.
- [ ] Commit `chore: bootstrap application configuration`.

### Task 2: Create typed domain mappings and Alembic schema

**Files:** Create `backend/app/models/{base,order,anomaly,dispatch,task,audit}.py`, `backend/app/repositories/*.py`, `backend/alembic/`; test `backend/tests/test_models.py`.

**Interfaces:** Produces `Dispatch`, `DispatchTask`, `IdempotencyRecord`, repository methods `create_or_get_task` and `apply_dispatch`.

- [ ] Write tests for required task identities, unique idempotency keys, Decimal values, and two independent sessions modifying one versioned dispatch.
- [ ] Run the version test; expect failure because mappings do not exist.
- [ ] Implement SQLAlchemy mappings with `version_id_col`, transactions, Alembic initial migration, and repositories that surface `StaleDataError` as `DispatchConflict`.
- [ ] Rerun model tests against MySQL test container; expect version A to become 6 and B to fail.
- [ ] Commit `feat: add durable domain schema and optimistic dispatch lock`.

### Task 3: Implement Provider interfaces and resilient adapters

**Files:** Create `backend/app/providers/llm/{base,openai_compatible,fake}.py`, `backend/app/providers/embedding/{base,openai_compatible,fake}.py`, `backend/app/providers/factory.py`, `backend/app/providers/environment.py`; test `backend/tests/test_providers.py`.

**Interfaces:** Produces async `LLMProvider.complete`, `EmbeddingProvider.embed`, `EnvironmentProvider.get_risk`, and typed provider errors.

- [ ] Write tests proving fake providers make no network call; assert independent provider configuration; simulate httpx timeout and open circuit.
- [ ] Run provider tests; expect failure because interfaces are absent.
- [ ] Implement narrow protocols, OpenAI-Compatible HTTP clients with configured timeouts, error normalization, breaker state, and static route fallback recording elapsed time.
- [ ] Rerun provider tests; assert fallback is selected before one second.
- [ ] Commit `feat: add pluggable AI and environment providers`.

### Task 4: Implement real Qdrant Entity-Relation memory

**Files:** Create `backend/app/memory/{schema,repository,service}.py`; test `backend/tests/test_memory_recall.py`.

**Interfaces:** Produces `MemoryResult(memory_id, similarity_score, historical_resolution, metadata)` and `EntityMemoryService.search`.

- [ ] Write a Qdrant integration test that stores 李师傅雨天经过新平路容易湿滑，历史建议改走 102 国道 and queries a similar rain/slippery-road anomaly using `FakeEmbeddingProvider` deterministic vectors.
- [ ] Run the test against Qdrant; expect failure because collection/service is absent.
- [ ] Implement collection creation, payload schema, vector upsert, score-ordered query, and evidence formatting; forbid an ID-only retrieval path.
- [ ] Rerun the test; assert top-1 resolution and similarity are returned.
- [ ] Commit `feat: add vector entity-resolution memory`.

### Task 5: Build graph state, agent ports, and seven node graph

**Files:** Create `backend/app/graph/{state,build,ports}.py`, `backend/app/agents/{intake,memory,environment,capacity,routing,dispatch,audit}.py`; tests `backend/tests/test_graph_state.py`, `backend/tests/test_dispatch_flow.py`.

**Interfaces:** Produces `DispatchGraphState`, `build_dispatch_graph`, and seven typed node callables.

- [ ] Write tests for state validation, seven-node order, memory evidence reaching Routing, fallback propagation, and audit routing a failed decision to manual review.
- [ ] Run graph tests; expect failure because graph assembly is absent.
- [ ] Implement graph nodes against ports only, with structured state updates and persisted AgentRun events; Routing must quote selected historical resolution in `decision_reason`.
- [ ] Rerun graph tests with fake providers/repositories; assert all node states and outcomes.
- [ ] Commit `feat: add typed seven-agent dispatch graph`.

### Task 6: Implement Redis publisher, group worker, and recovery

**Files:** Create `backend/app/streams/{publisher,consumer,recovery,retry,idempotency,events}.py`, `backend/app/worker.py`; tests `backend/tests/test_stream_{publish,consumer_group,worker_retry,worker_idempotency,pending_recovery}.py`.

**Interfaces:** Produces `TaskPublisher.enqueue`, `DispatchWorker.run`, `recover_pending`, and `TaskEventPublisher.publish`.

- [ ] Write real Redis integration tests for XADD/group consumption/XACK, crash-like unacked pending delivery, exponential retry, duplicate keys, and cancelled worker shutdown.
- [ ] Run the stream tests against Redis; expect failure because queue code is absent.
- [ ] Implement group creation, XREADGROUP, durable attempt checks, XAUTOCLAIM recovery, dead-letter handling, idempotent task lookup, and `CancelledError` re-raise behavior.
- [ ] Rerun stream tests; assert one dispatch at most and ACK only after terminal persistence.
- [ ] Commit `feat: add recoverable Redis Streams worker`.

### Task 7: Expose task APIs, dispatch conflict handling, and WebSocket events

**Files:** Create `backend/app/api/{router,tasks,orders,anomalies,dispatches,websocket}.py`; tests `backend/tests/test_api_{tasks,conflict,degradation,websocket}.py`.

**Interfaces:** Produces task submission/status endpoints, HTTP 409 conflict contract, and `/ws/tasks/{task_id}` event protocol.

- [ ] Write API tests ensuring submission XADDs without graph execution, duplicate key returns same task, stale update is 409, degradation fields are visible, and WebSocket sends snapshot then ordered events.
- [ ] Run API tests with real Redis/MySQL dependencies; expect failure because endpoints are absent.
- [ ] Implement request validation, services, safe status serialization, authorization hook, snapshot/replay, bounded WebSocket buffers, and HTTP exception mapping.
- [ ] Rerun API tests; assert no secret or provider stack trace is exposed.
- [ ] Commit `feat: expose asynchronous dispatch APIs and task events`.

### Task 8: Create operational Compose topology and health validation

**Files:** Create `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `backend/app/api/health.py`, deployment docs; tests `backend/tests/test_health.py`.

**Interfaces:** Produces health/readiness endpoints and compose service names `frontend`, `backend`, `worker`, `redis`, `mysql`, `qdrant`.

- [ ] Write health tests for dependency status shape and compose configuration assertions for volumes, health checks, and worker restart policy.
- [ ] Run tests; expect failure because topology is absent.
- [ ] Implement Docker images, named volumes, health checks, health-aware dependencies, worker `unless-stopped`, and non-secret environment interpolation.
- [ ] Run `docker compose config` and targeted health tests; record actual output.
- [ ] Commit `feat: add deployable compose topology`.

### Task 9: Build approved React design system and app shell

**Files:** Create `frontend/src/{app,components,styles,types}/`, Vite/Tailwind config; tests under `frontend/tests/`.

**Interfaces:** Produces tokens, `AppShell`, sidebar routes, table, status badge, chart palette, and reduced-motion rules.

- [ ] Write component tests for navigation, accessible statuses, table semantics, and reduced-motion behavior.
- [ ] Run frontend tests; expect failure because components are absent.
- [ ] Implement the exact design tokens and shell from `docs/design.md`; use Lucide icons and no emoji.
- [ ] Run lint, tests, production build, and browser screenshot comparison to the generated concept once it is available.
- [ ] Commit `feat: add operations console design system`.

### Task 10: Implement console workflows with real APIs

**Files:** Create feature modules for dashboard, anomalies, dispatch, orders, agents, memory, monitoring; tests for feature flows.

**Interfaces:** Produces query hooks, dispatch detail graph display, memory search, filters, task submission, and WebSocket reconnection.

- [ ] Write feature tests for anomaly filtering/navigation, task submission, graph status transitions, fallback display, memory detail, and conflict display.
- [ ] Run feature tests; expect failure because flows are absent.
- [ ] Implement TanStack Query services, tables/drawers, three-column dispatch workspace, charts, and event-state reducer with reconnect/resync.
- [ ] Run frontend lint/test/build and browser interaction checks at 1366×768, 1440px, and 1920px.
- [ ] Commit `feat: add interactive logistics control console`.

### Task 11: Add end-to-end tests, Locust, and operational review

**Files:** Create `loadtests/locustfile.py`, `docs/ai-review.md`, `docs/pressure-test-report.md`, `docs/project-retrospective.md`; modify CI/Makefile.

**Interfaces:** Produces reproducible test and report commands, not invented results.

- [ ] Write Compose end-to-end tests for submit-to-worker-to-WebSocket flow and Locust task definitions for required read/write scenarios.
- [ ] Run E2E tests; expect failure until all composed services are ready.
- [ ] Implement Locust users with order list/detail, anomaly list/bulk, concurrent dispatch, and task status; add check targets and document review categories.
- [ ] Run the required suite and a measured Locust run; record command, environment, duration, QPS/P95/error output, or explicitly state a run could not execute.
- [ ] Commit `test: add e2e load and operational review coverage`.

## Plan self-review

Coverage: Tasks 1–3 establish safe configuration/providers; 2 covers database truth and locking; 4 covers genuine Qdrant recall; 5 covers all seven typed agents; 6 covers group/ACK/pending/retry/idempotency; 7 covers API/WebSocket/fallback status; 8 covers Docker; 9–10 cover the approved UI; 11 covers Locust/reports. No placeholder terms or unbound interfaces are used; every referenced public interface is introduced in its task. The plan avoids microservice and provider overdesign.
