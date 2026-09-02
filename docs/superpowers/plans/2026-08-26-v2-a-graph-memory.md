# CountyFlow V2-A Graph Memory Implementation Plan

> **For agentic workers:** Execute inline in the current user-owned workspace. Use strict RED -> confirm failure -> GREEN -> REFACTOR cycles. Do not commit or create a worktree because this repository has no commits and the user requires preserving its current Git state.

**Goal:** Add real Neo4j relationship memory, a safely degrading Graph Memory Agent, and an eight-agent V2-A pipeline without changing V1 routing behavior.

**Architecture:** Keep Qdrant semantic recall intact and add an independent repository/service boundary for bounded Neo4j graph recall. Inject the service through `GraphDependencies`, emit serializable state/event evidence, and run real Neo4j only in Docker-backed integration validation.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, official Neo4j Python driver, Neo4j Community, pytest, React/TypeScript/Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-26-v2-a-graph-memory-design.md`

## Global constraints

- Preserve MySQL, Qdrant, Redis Streams, workers, FastAPI, WebSocket, dispatch, audit, and V1 routing results.
- Values in Cypher are parameters; labels and relationship types come only from enums/allowlists.
- State remains typed and JSON serializable; infrastructure objects remain in dependencies.
- Graph traversal is limited to 1-3 hops, defaults to two, has a result cap and timeout.
- Neo4j failure degrades Graph Memory only and never catches cancellation.
- Do not implement Runtime Override, checkpoint mutation, memory merge/conflicts, approval intervention, TTL/forgetting, or LLM extraction.

---

### Task 1: Domain contracts and deterministic extraction

**Files:** create `backend/app/graph_memory/models.py`, `protocols.py`, `extractor.py`, `fake_repository.py`; add focused tests under `backend/tests/graph_memory/`.

- [ ] Write tests that reject injected entity/relation types and validate frozen serializable entities, relations, paths, and recalls.
- [ ] Run tests and confirm missing modules/contracts fail.
- [ ] Add enums, dataclasses, protocol, errors, deterministic extractor, and fake bounded graph repository.
- [ ] Run focused tests to green and refactor without expanding scope.

### Task 2: Graph service and recall behavior

**Files:** create `backend/app/graph_memory/service.py`; test extraction, relation recall, two-hop recall, limits, and query timing.

- [ ] Write behavior tests for the core Chinese text and graph recall, including that `national-102` is recalled rather than extracted.
- [ ] Confirm failures, implement minimal service orchestration, and rerun focused tests.
- [ ] Verify 1-3 hop validation and result cap behavior.

### Task 3: Real Neo4j repository, schema, and seed

**Files:** create `neo4j_repository.py`, `schema.py`, `seed.py`; modify `backend/pyproject.toml`; add unit contract/Cypher tests.

- [ ] Write tests around parameterized Cypher, allowlist validation, driver-object isolation, idempotent schema statements, and idempotent seed behavior.
- [ ] Confirm failures, add official driver dependency and repository implementation, then rerun tests.
- [ ] Keep transaction/error mapping within the repository boundary.

### Task 4: Agent, state, dependencies, topology, event, and audit

**Files:** create `backend/app/agents/graph_memory.py`; modify graph state/dependencies/builder, event models/adapter, and audit evidence.

- [ ] Write failing tests for agent success/degradation, JSON serialization, dependency isolation, eight-node topology, event lifecycle/degradation, and compact audit evidence.
- [ ] Implement the smallest patches and rerun focused graph/event/audit regression tests.
- [ ] Confirm routing behavior remains unchanged.

### Task 5: Runtime settings and factories

**Files:** modify config/runtime/worker entrypoint/main health, `.env.example`, `.docker.env.example`.

- [ ] Write failing tests for secret-safe settings, docker/production real-store requirements, local optional mode, runtime summary, and runtime graph injection.
- [ ] Implement settings and Neo4j lifecycle construction/closure without exposing credentials.
- [ ] Rerun settings/runtime/health tests.

### Task 6: Docker service and real integration tooling

**Files:** modify `docker-compose.yml`, backend container dependencies/lock; create `scripts/test-graph-memory.ps1` and a Python integration runner.

- [ ] Write failing executable/config behavior tests for the ninth service, health dependency, persistent volume, environment wiring, and integration runner boundaries.
- [ ] Add Neo4j Community service, bootstrap/seed command, and real-server integration/timing script.
- [ ] Validate `docker compose config` before full Docker execution.

### Task 7: Frontend eight-agent pipeline and evidence block

**Files:** modify task event hook/types, mock data/playback, agents page, API dispatch detail, mock dispatch detail, and tests.

- [ ] Write failing tests for Graph Memory ordering, started/completed/degraded status, eight-agent playback, and event-driven evidence display.
- [ ] Implement minimal UI/type changes without redesigning the application.
- [ ] Run focused Vitest, lint, and build.

### Task 8: Documentation and full verification

**Files:** create/update `docs/memory_spec.md`, `docs/design.md`, and verification output only from actual commands.

- [ ] Document memory boundaries, schemas, security, seed, degradation, query bounds, and deferred phases.
- [ ] Run backend Ruff and full pytest and record actual count.
- [ ] Run frontend lint/test/build and record actual count.
- [ ] Run `scripts/check.ps1`.
- [ ] Run Docker config/build/up/status, real Neo4j integration, core V1 E2E, and graph timing smoke.
- [ ] Run the existing secret scan and `git diff --check`, `git diff --cached --check`, and `git status`.
- [ ] Compare every V2-A acceptance item with evidence; report COMPLETE only if all mandatory checks pass.

