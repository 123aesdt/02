# CountyFlow V2-C Persistent Checkpoint and Thread State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not use subagents unless the user explicitly authorizes delegation for the implementation session.

**Goal:** Add durable LangGraph checkpoints and stable thread state so a second worker resumes the accepted eight-agent dispatch from the node after the last canonical checkpoint, with read-only inspection and no V1/V2-A/V2-B regression.

**Architecture:** Compile the existing graph with the official `AsyncRedisSaver`, execute with synchronous durability and a stable server-derived `thread_id`, then promote each post-node Redis checkpoint into a lightweight MySQL canonical pointer using compare-and-swap. `CheckpointedGraphRunner` stops before the next node if registry promotion fails; `ThreadCheckpointReconciler` may promote one verified orphan. MySQL holds registry/audit metadata only, while full immutable checkpoint payloads remain in Redis.

**Tech Stack:** Python 3.12, LangGraph 1.2.x, `langgraph-checkpoint` 4.2.x, `langgraph-checkpoint-redis` 0.5.x, Redis 8, FastAPI, Pydantic, SQLAlchemy 2, Alembic, MySQL 8.4, pytest, React/TypeScript/Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-27-v2-c-checkpoint-design.md`

## Global constraints

- This plan implements V2-C only. Do not add runtime override, `update_state`, checkpoint mutation, pause/resume command endpoints, rollback, branch editing, target-node mutation, human approval, thread mutation locks, or memory merge.
- Preserve the eight-agent topology and routing algorithm exactly.
- Keep `DispatchGraphState` typed and JSON serializable. Never place a Redis client, checkpointer, SQLAlchemy session/factory, Neo4j/Qdrant client, repository, service, lock, or event broker in state.
- Use the official full-history async Redis saver. Do not substitute `AsyncShallowRedisSaver` or a custom saver.
- Use `durability="sync"` for all checkpointed production graph execution.
- MySQL `current_checkpoint_id` is canonical. Never expose “latest Redis checkpoint” without registry validation.
- Redis checkpoint persistence must precede the MySQL pointer transaction. Never reverse the order.
- Keep complete checkpoint payloads out of MySQL, task events, logs, and API errors.
- Use server-generated thread IDs matching `cf:dispatch:TASK-...`; never trust a caller-provided thread ID for task creation.
- Keep Docker at nine services. Upgrade the existing Redis service; do not add a checkpoint service.
- Preserve user-owned work. Do not stage or commit in this repository unless the user explicitly asks.
- For every task: write the behavior test, run it and record the expected failure, implement the smallest real behavior, rerun, refactor only with green tests, then run the stated regression.

## Planned file map

### Backend runtime-thread domain

- Create `backend/app/runtime_threads/__init__.py`
- Create `backend/app/runtime_threads/models.py`
- Create `backend/app/runtime_threads/identity.py`
- Create `backend/app/runtime_threads/protocols.py`
- Create `backend/app/runtime_threads/sqlalchemy_repository.py`
- Create `backend/app/runtime_threads/checkpoint_store.py`
- Create `backend/app/runtime_threads/runner.py`
- Create `backend/app/runtime_threads/reconciler.py`
- Create `backend/app/runtime_threads/service.py`
- Create `backend/app/runtime_threads/auth.py`
- Create `backend/app/runtime_threads/events.py`

### Existing backend files

- Modify `backend/pyproject.toml`
- Modify `backend/app/core/config.py`
- Modify `backend/app/models/task.py`
- Create `backend/app/models/runtime_thread.py`
- Modify `backend/app/models/__init__.py`
- Create `backend/alembic/versions/20260827_04_runtime_threads.py`
- Modify `backend/app/graph/state.py`
- Modify `backend/app/graph/builder.py`
- Modify `backend/app/events/models.py`
- Modify `backend/app/events/graph_adapter.py`
- Modify `backend/app/workers/dispatch_worker.py`
- Modify `backend/app/services/dispatch_task_api_service.py`
- Create `backend/app/api/v1/runtime_threads.py`
- Create `backend/app/api/v1/runtime_thread_schemas.py`
- Modify `backend/app/runtime.py`
- Modify `backend/app/main.py`
- Modify `backend/app/worker_entrypoint.py`

### Tests and acceptance

- Create `backend/tests/runtime_threads/test_registry.py`
- Create `backend/tests/runtime_threads/test_graph_checkpointing.py`
- Create `backend/tests/runtime_threads/test_resume.py`
- Create `backend/tests/runtime_threads/test_consistency.py`
- Create `backend/tests/runtime_threads/test_service.py`
- Create `backend/tests/runtime_threads/test_events.py`
- Create `backend/tests/api/test_runtime_threads.py`
- Modify `backend/tests/unit/test_settings.py`
- Modify `backend/tests/unit/test_docker_runtime_files.py`
- Modify `backend/tests/workers/test_dispatch_worker.py`
- Create `backend/tests/integration/test_real_redis_checkpointer.py`
- Create `scripts/checkpoint_integration.py`
- Create `scripts/docker_checkpoint_recovery_e2e.py`
- Create `scripts/test-checkpoint.ps1`
- Modify `scripts/test-docker.ps1`

### Frontend

- Create `frontend/src/types/runtime-thread.ts`
- Create `frontend/src/services/api/runtime-thread-client.ts`
- Create `frontend/src/hooks/use-runtime-thread.ts`
- Create `frontend/src/components/runtime-thread-panel.tsx`
- Modify `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify `frontend/src/config/runtime.ts`
- Modify `frontend/src/styles/index.css`
- Create `frontend/tests/runtime-thread-panel.test.tsx`
- Modify `frontend/.env.example` if present; otherwise modify root `.env.example`

### Documentation and evidence

- Modify `README.md`
- Modify `.docker.env.example`
- Modify `docs/design.md` only if implementation evidence changes a stated detail
- Create `docs/verification/v2-c-checkpoint-results.md`
- Create `docs/verification/raw/v2-c-checkpoint-performance.json`
- Modify `docs/superpowers/plans/2026-08-27-v2-c-checkpoint.md` checkboxes during execution

---

## Task 1: Pin the official saver and verify the existing Redis service can support it

**Files:**

- Modify `backend/pyproject.toml`
- Modify `docker-compose.yml`
- Modify `.docker.env.example`
- Modify `backend/app/core/config.py`
- Modify `backend/tests/unit/test_settings.py`
- Modify `backend/tests/unit/test_docker_runtime_files.py`

**Interfaces and settings:**

```text
langgraph-checkpoint-redis>=0.5.2,<0.6
RUNTIME_CHECKPOINT_BACKEND=redis
RUNTIME_CHECKPOINT_RETENTION_MINUTES=10080
RUNTIME_CHECKPOINT_REFRESH_ON_READ=false
RUNTIME_CHECKPOINT_MAX_BYTES=1048576
```

- [x] **Step 1.1 — RED: write settings and Compose contract tests**

Add assertions that docker-dev/production require `runtime_checkpoint_backend=redis`, retention and size are positive, the Compose service count remains nine, the Redis image is exactly `redis:8.2.9-alpine`, AOF remains enabled, and no `checkpoint` service is declared.

- [x] **Step 1.2 — Confirm RED**

Run:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/unit/test_settings.py tests/unit/test_docker_runtime_files.py -q
```

Expected: fail because checkpoint settings/dependency and Redis 8 contract are absent.

- [x] **Step 1.3 — GREEN: add the minimal dependency, settings, and image change**

Add the pinned saver dependency and upgrade only the existing Redis image. Retain `redis-server --appendonly yes`, ports, volume, health check, and networks. Do not change the service list.

- [x] **Step 1.4 — Verify package resolution and imports**

After installing the updated backend dependencies, run:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -c "from langgraph.checkpoint.redis.aio import AsyncRedisSaver; import importlib.metadata as m; print(m.version('langgraph-checkpoint-redis')); print(m.version('langgraph-checkpoint'))"
```

Expected: saver import succeeds; the installed versions satisfy saver 0.5.x and checkpoint 4.x.

- [x] **Step 1.5 — REFACTOR and regression**

Run the two test files again, then `..\.venv\Scripts\python.exe -m ruff check app tests/unit/test_settings.py tests/unit/test_docker_runtime_files.py`.

---

## Task 2: Define thread identity, immutable snapshots, statuses, and narrow protocols

**Files:**

- Create `backend/app/runtime_threads/__init__.py`
- Create `backend/app/runtime_threads/models.py`
- Create `backend/app/runtime_threads/identity.py`
- Create `backend/app/runtime_threads/protocols.py`
- Create `backend/tests/runtime_threads/test_registry.py`

**Interfaces:**

```python
class RuntimeThreadStatus(StrEnum):
    RUNNING = "RUNNING"
    STABLE = "STABLE"
    TERMINAL = "TERMINAL"

def thread_id_for_task(task_id: str) -> str: ...

@dataclass(frozen=True)
class RuntimeThreadSnapshot: ...

@dataclass(frozen=True)
class PromoteCheckpoint: ...

class RuntimeThreadRepository(Protocol): ...
class RuntimeCheckpointStore(Protocol): ...
class RuntimeThreadAuthorizer(Protocol): ...
```

- [x] **Step 2.1 — RED: add identity and validation tests**

Test deterministic distinct IDs, rejection of malformed task IDs, frozen snapshots, allowed statuses, nonnegative versions, bounded node names, and rejection of secret/error payload fields.

- [x] **Step 2.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_registry.py -q` from `backend`.

Expected: collection fails because the runtime-thread package does not exist.

- [x] **Step 2.3 — GREEN: implement pure types and protocols**

Use dataclasses/enums and no infrastructure imports in `models.py`, `identity.py`, or `protocols.py`.

- [x] **Step 2.4 — REFACTOR and regression**

Run the test file and Ruff. Inspect imports to confirm the domain layer does not import Redis, SQLAlchemy, Qdrant, or Neo4j.

---

## Task 3: Add the MySQL registry and append-only metadata ledger

**Files:**

- Create `backend/app/models/runtime_thread.py`
- Modify `backend/app/models/__init__.py`
- Create `backend/alembic/versions/20260827_04_runtime_threads.py`
- Create `backend/app/runtime_threads/sqlalchemy_repository.py`
- Modify `backend/app/services/dispatch_task_api_service.py`
- Modify `backend/app/idempotency/service.py` only as required to create task and thread in one transaction
- Modify `backend/tests/conftest.py` only if model import discovery requires it
- Modify `backend/tests/runtime_threads/test_registry.py`

**Mandatory tests delivered:**

- `test_thread_registry_create`
- `test_thread_id_stable_across_worker_retry`
- `test_checkpoint_history_append_only`
- `test_current_checkpoint_pointer`
- `test_state_version_increments`
- `test_terminal_thread_marked`

- [x] **Step 3.1 — RED: write the six mandatory repository behaviors**

Assertions:

- task creation creates exactly one registry row at version 0;
- a retry or duplicate submission reuses the same `thread_id`;
- promotion inserts rather than updates/deletes an event row;
- only the promoted checkpoint becomes current;
- two accepted promotions produce versions 1 then 2;
- terminal transition is idempotent and records `terminal_at` without an extra checkpoint version.
- `DLQ` terminalizes the thread at its last stable pointer, while retryable graph failure and `SUBMISSION_FAILED` do not prematurely terminalize it.

- [x] **Step 3.2 — Confirm RED**

Run:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_registry.py -q
```

Expected: fail for missing models/repository/migration.

- [x] **Step 3.3 — GREEN: implement additive models and migration**

Use `row_version` as SQLAlchemy `version_id_col`, a separate canonical `state_version`, unique task/thread constraints, an operation-specific unique `event_key`, and indexed thread/version history. Maintain `checkpoint_count` and `last_event_sequence`; expose `terminal` as a derived property. Do not store checkpoint JSON.

- [x] **Step 3.4 — GREEN: create task and registry atomically**

Refactor the narrow task-creation transaction so the new `DispatchTask` and `RuntimeThread` are committed together. Existing duplicate/idempotency behavior and queue publication order must remain unchanged.

- [x] **Step 3.5 — REFACTOR: translate stale updates**

Translate `StaleDataError`/failed compare-and-swap to `ThreadVersionConflict`. Make duplicate promotion idempotent only when thread, checkpoint, parent, node, and resulting version agree.

- [x] **Step 3.6 — Regression**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_registry.py tests/api/test_dispatch_tasks.py tests/workers/test_worker_idempotency.py -q
..\.venv\Scripts\python.exe -m ruff check app tests
```

Expected: all pass.

---

## Task 4: Inject a native checkpointer and create explicit post-node boundaries

**Files:**

- Modify `backend/app/graph/state.py`
- Modify `backend/app/graph/builder.py`
- Create `backend/tests/runtime_threads/test_graph_checkpointing.py`
- Modify `backend/tests/graph_memory/test_topology.py`

**Mandatory tests delivered:**

- `test_checkpoint_after_node`
- `test_checkpoint_payload_serializable`
- `test_checkpoint_excludes_dependencies`

- [x] **Step 4.1 — RED: write native checkpoint tests with `InMemorySaver`**

`test_checkpoint_after_node` compiles a deterministic graph, invokes through one node with static `interrupt_after`, and asserts a checkpoint exists with the expected `last_completed_node` and next node.

`test_checkpoint_payload_serializable` walks every checkpoint state value through `json.dumps`.

`test_checkpoint_excludes_dependencies` recursively rejects modules/classes from Redis, SQLAlchemy, Qdrant, Neo4j, and CountyFlow repository/service packages.

- [x] **Step 4.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_graph_checkpointing.py tests/graph_memory/test_topology.py -q`.

Expected: fail because `build_graph` has no checkpointer argument and node-boundary fields are absent.

- [x] **Step 4.3 — GREEN: add instrumented node wrappers**

Wrap each existing node callable at graph construction. After a successful node result, add only `last_completed_node` and increment `completed_node_count`. Do not modify the node's business logic, routing result, or edge order.

- [x] **Step 4.4 — GREEN: expose compile-time runtime options**

Add keyword-only `checkpointer`, `interrupt_before`, and `interrupt_after` parameters and pass them directly to `StateGraph.compile`. Default `None` preserves existing unit-test behavior.

- [x] **Step 4.5 — REFACTOR and regression**

Run all graph tests. Assert the exact ordered node list is still eight nodes and every existing final-state assertion is unchanged.

---

## Task 5: Build the official saver adapter and exact read boundary

**Files:**

- Create `backend/app/runtime_threads/checkpoint_store.py`
- Create `backend/tests/runtime_threads/test_service.py`
- Create `backend/tests/integration/test_real_redis_checkpointer.py`

**Interfaces:**

```python
class RedisRuntimeCheckpointStore:
    @classmethod
    async def from_url(cls, url: str, *, ttl_minutes: int, refresh_on_read: bool): ...
    async def setup(self) -> None: ...
    async def get_exact(self, thread_id: str, checkpoint_id: str): ...
    async def list_bounded(self, thread_id: str, limit: int): ...
    def serialized_size(self, checkpoint: object) -> int: ...
    async def close(self) -> None: ...
```

- [x] **Step 5.1 — RED: write adapter tests**

Unit tests prove exact checkpoint lookup never falls back to latest, history honors limit, size is measured with the configured serializer, and safe records contain no saver/client object.

- [x] **Step 5.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_service.py -q`.

- [x] **Step 5.3 — GREEN: implement the narrow adapter**

Wrap `AsyncRedisSaver`; call `asetup()` once per process startup. Use empty `checkpoint_ns`. Normalize vendor exceptions without URLs or credentials.

- [x] **Step 5.4 — RED/GREEN: real Redis protocol smoke**

Against the Docker Redis service, call saver setup, compile a two-node graph, persist, exact-read, list history, resume, and delete the disposable thread. Confirm RedisJSON/search capabilities through successful setup rather than parsing image marketing text.

- [x] **Step 5.5 — Regression**

Run the unit test and targeted real integration test. Do not run the real test against fakeredis.

---

## Task 6: Implement canonical promotion and stop-before-next-node behavior

**Files:**

- Create `backend/app/runtime_threads/runner.py`
- Create `backend/tests/runtime_threads/test_consistency.py`
- Modify `backend/app/events/graph_adapter.py`

**Mandatory test delivered:**

- `test_checkpoint_registry_partial_failure`

**Runner contract:**

```python
async def run_new(thread: RuntimeThreadSnapshot, state: DispatchGraphState) -> Mapping[str, object]: ...
async def resume(thread: RuntimeThreadSnapshot) -> Mapping[str, object]: ...
```

- [x] **Step 6.1 — RED: simulate Redis success and repository promotion failure**

Use a two-node counting graph. Let saver persistence succeed after node A, make the repository fail promotion, and assert:

- Redis contains A's checkpoint;
- MySQL/fake registry still points to its previous checkpoint;
- B was never called;
- no checkpoint event was published;
- the runner raises a normalized retryable error.

- [x] **Step 6.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_consistency.py::test_checkpoint_registry_partial_failure -q`.

- [x] **Step 6.3 — GREEN: implement synchronous streaming and promotion**

Invoke `graph.astream(..., stream_mode="updates", durability="sync")`. After each known node update, load the latest snapshot, validate boundary metadata/size/topology, then call repository promotion before fetching another stream item.

- [x] **Step 6.4 — REFACTOR event order**

Split `GraphEventAdapter` so the runner can publish node-completed and checkpoint events only after promotion. Preserve all existing environment fallback, graph-memory degradation, routing, and node-start events.

- [x] **Step 6.5 — Regression**

Run consistency, graph-event, task-event, and worker tests. Confirm an event-broker failure still does not roll back a canonical checkpoint.

---

## Task 7: Reconcile one verified orphan checkpoint

**Files:**

- Create `backend/app/runtime_threads/reconciler.py`
- Modify `backend/tests/runtime_threads/test_consistency.py`

**Mandatory test delivered:**

- `test_checkpoint_reconciliation`

- [x] **Step 7.1 — RED: write safe and unsafe orphan cases**

The mandatory test creates a current canonical A checkpoint plus one Redis B checkpoint whose parent/count/node/next-node are valid, then asserts reconciliation promotes B exactly once.

Add negative cases for wrong parent, wrong thread, skipped count, unknown node, excessive payload, multiple divergent children, and an already-promoted checkpoint.

- [x] **Step 7.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_consistency.py::test_checkpoint_reconciliation -q`.

- [x] **Step 7.3 — GREEN: implement bounded reconciliation**

Inspect at most `RUNTIME_THREAD_RECONCILIATION_SCAN_LIMIT=10` newest records. Promote only the unique verified next post-node checkpoint. Append `THREAD_RECONCILED`; do not delete ambiguous Redis records.

- [x] **Step 7.4 — REFACTOR and regression**

Run the complete consistency test file and verify errors expose safe codes only.

---

## Task 8: Resume the graph from the canonical checkpoint

**Files:**

- Create `backend/tests/runtime_threads/test_resume.py`
- Modify `backend/app/runtime_threads/runner.py`

**Mandatory tests delivered:**

- `test_resume_from_latest_checkpoint`
- `test_resume_does_not_repeat_completed_nodes`

- [x] **Step 8.1 — RED: write deterministic resume tests**

Use three counting nodes. Persist/promote after B, construct a fresh graph instance with the same saver, resume with `input=None` and exact canonical `checkpoint_id`, and assert C runs while A/B counters remain unchanged.

- [x] **Step 8.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_resume.py -q`.

- [x] **Step 8.3 — GREEN: implement exact canonical resume**

Call the graph with config containing the registry thread/checkpoint IDs. Record one idempotent `THREAD_RESUMED` registry event and increment `resumed_count` only after the resumed stream begins successfully.

- [x] **Step 8.4 — API compatibility test for native interrupts**

Add a non-mandatory test proving installed LangGraph static resume uses `None` and dynamic `interrupt()` uses `Command(resume=value)`. Keep it isolated from production CountyFlow nodes.

- [x] **Step 8.5 — Regression**

Run graph checkpointing and resume files together.

---

## Task 9: Wire worker recovery without duplicate dispatch or audit

**Files:**

- Modify `backend/app/workers/dispatch_worker.py`
- Modify `backend/app/runtime.py`
- Modify `backend/app/worker_entrypoint.py`
- Modify `backend/tests/workers/test_dispatch_worker.py`
- Modify `backend/tests/workers/test_pending_recovery.py`
- Modify `backend/tests/workers/test_worker_idempotency.py`
- Modify `backend/tests/runtime_threads/test_resume.py`

**Mandatory tests delivered:**

- `test_resume_no_duplicate_dispatch`
- `test_resume_no_duplicate_audit`

- [x] **Step 9.1 — RED: write crash-window business tests**

Persist a canonical checkpoint after dispatch and separately after audit, recreate the worker/runner, resume the same pending message, and assert database counts stay at one dispatch and one audit. Assert V2-B `memory_mutations` count does not change.

- [x] **Step 9.2 — Confirm RED**

Run the two named tests and existing worker idempotency tests. Expected: the worker has no runner/thread boundary yet.

- [x] **Step 9.3 — GREEN: replace direct graph invocation with runner invocation**

The worker loads the registry by task, reconciles terminal business truth first, reconciles one safe checkpoint, and calls `run_new` or `resume`. Keep execution lock acquisition, retry policy, DLQ, cancellation, terminal persistence, and ACK ordering unchanged.

- [x] **Step 9.4 — GREEN: terminal lifecycle**

After a terminal graph state, mark the registry terminal idempotently, then mark the task terminal, publish terminal events, and ACK. A final DLQ transition also terminalizes the thread at its last stable pointer with a normalized error; retryable failure does not. If registry terminal marking fails, leave the message pending.

- [x] **Step 9.5 — REFACTOR and regression**

Run every test under `tests/workers`, `tests/streams`, `tests/runtime_threads`, and the existing graph suite.

---

## Task 10: Add safe checkpoint events and durable metadata audit

**Files:**

- Modify `backend/app/events/models.py`
- Create `backend/app/runtime_threads/events.py`
- Create `backend/tests/runtime_threads/test_events.py`
- Modify `backend/tests/api/test_task_events.py`
- Modify `frontend/src/types/task-events.ts`

**Mandatory test delivered:**

- `test_checkpoint_event`

- [x] **Step 10.1 — RED: write safe payload and ordering assertions**

Assert `THREAD_CHECKPOINTED` occurs after the corresponding node completion has a canonical pointer, carries version/checkpoint/node/next/size only, and contains no state, anomaly description, memory evidence, URL, Authorization, or exception text.

- [x] **Step 10.2 — Confirm RED**

Run `..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_events.py tests/api/test_task_events.py -q`.

- [x] **Step 10.3 — GREEN: extend events through one adapter**

Use a runtime-thread event publisher to produce task-broker events from committed registry snapshots. Add `THREAD_RESUMED` and `THREAD_TERMINAL` with the same allowlisted payload builder. After a successful broker publish, persist its returned sequence as `last_event_sequence` through an idempotent metadata update.

- [x] **Step 10.4 — REFACTOR and regression**

Run all event, WebSocket, cross-instance event, and frontend event parsing tests.

---

## Task 11: Implement canonical read service and GET-only API

**Files:**

- Create `backend/app/runtime_threads/service.py`
- Create `backend/app/runtime_threads/auth.py`
- Create `backend/app/api/v1/runtime_thread_schemas.py`
- Create `backend/app/api/v1/runtime_threads.py`
- Modify `backend/app/main.py`
- Modify `backend/tests/runtime_threads/test_service.py`
- Create `backend/tests/api/test_runtime_threads.py`
- Modify `backend/tests/unit/test_settings.py`

**Mandatory tests delivered:**

- `test_thread_read_api`
- `test_thread_history_api`
- `test_production_runtime_api_requires_auth`

- [x] **Step 11.1 — RED: write service tests**

Assert current reads load the registry first and then exact checkpoint ID. A newer orphan in Redis must remain invisible. Missing/expired payload returns explicit availability metadata. History is canonical, append-only, version-ordered, and bounded.

- [x] **Step 11.2 — RED: write GET-only API tests**

Test by-task and by-thread reads, history limit/max-limit, 404, 503, unauthorized, disabled router, and absence of mutation routes. Verify response schemas contain only JSON values.

- [x] **Step 11.3 — RED: write production configuration guard**

`test_production_runtime_api_requires_auth` must reject production settings when the API is enabled with the disabled authorization provider.

- [x] **Step 11.4 — Confirm RED**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/runtime_threads/test_service.py tests/api/test_runtime_threads.py tests/unit/test_settings.py -q
```

- [x] **Step 11.5 — GREEN: implement the service, schemas, authorizer, and feature-gated router**

Mount only GET routes when enabled. Put authorization before checkpoint-store access. Validate thread/task identifiers and cap limits at 100.

- [x] **Step 11.6 — REFACTOR and regression**

Run all backend API tests and secret-safety tests.

---

## Task 12: Add the minimal read-only frontend panel

**Files:**

- Create `frontend/src/types/runtime-thread.ts`
- Create `frontend/src/services/api/runtime-thread-client.ts`
- Create `frontend/src/hooks/use-runtime-thread.ts`
- Create `frontend/src/components/runtime-thread-panel.tsx`
- Modify `frontend/src/pages/api-dispatch-detail-page.tsx`
- Modify `frontend/src/config/runtime.ts`
- Modify `frontend/src/styles/index.css`
- Create `frontend/tests/runtime-thread-panel.test.tsx`
- Modify `.env.example`

- [x] **Step 12.1 — RED: write component and client tests**

Cover enabled/disabled, loading, stable, terminal, unauthorized, unavailable/expired, bounded history, and no mutation controls. Assert no button labelled pause/resume/rollback/override is rendered.

- [x] **Step 12.2 — Confirm RED**

Run:

```powershell
Set-Location frontend
npm test -- --run runtime-thread-panel
```

- [x] **Step 12.3 — GREEN: implement the typed read path**

Use the existing API client. Show the panel only for API mode with `VITE_RUNTIME_THREAD_STATE_ENABLED=true`. Keep task-event playback independent.

- [x] **Step 12.4 — REFACTOR and regression**

Run `npm run lint`, `npm test -- --run`, and `npm run build`.

---

## Task 13: Real Redis performance and retention evidence

**Files:**

- Expand `backend/tests/integration/test_real_redis_checkpointer.py`
- Create `scripts/checkpoint_integration.py`
- Create `scripts/test-checkpoint.ps1`
- Create `docs/verification/raw/v2-c-checkpoint-performance.json`

- [x] **Step 13.1 — RED: add a real-server gate**

The script must fail if it sees fakeredis, Redis without saver setup capability, fewer than 20 writes/reads, missing latency samples, or a checkpoint above the configured size limit.

- [x] **Step 13.2 — Confirm RED**

Run the script before its implementation or against the old Redis 7.4 service. Expected: explicit capability/dependency failure.

- [x] **Step 13.3 — GREEN: implement the benchmark**

Use disposable thread IDs. Perform 20 synchronous graph checkpoint writes and 20 exact reads. Compute minimum, average, nearest-rank P95, maximum, error count, and serialized size. Persist only measured numbers and safe version labels.

- [x] **Step 13.4 — Verify TTL behavior**

Use a short disposable retention in the targeted test, prove checkpoint keys expire, and prove reads do not refresh TTL when `refresh_on_read=false`. Do not change the normal seven-day setting for the test.

- [x] **Step 13.5 — Acceptance**

Set no new checkpoint-latency hard redline. Require zero operation errors and max size <=1 MiB, record all latency values, compare end-to-end behavior with the accepted Locust and worker-recovery evidence, and report any material slowdown instead of converting it into an invented pass/fail threshold.

---

## Task 14: Real two-worker crash and resume E2E

**Files:**

- Create `scripts/docker_checkpoint_recovery_e2e.py`
- Modify `scripts/test-docker.ps1`
- Modify `backend/tests/unit/test_docker_runtime_files.py`

- [x] **Step 14.1 — RED: add harness contract tests**

Static tests require the script to select a canonical node N, observe `THREAD_CHECKPOINTED`, kill Worker 1, wait for lock expiry/XAUTOCLAIM, and verify Worker 2 resumes N+1. The harness must query MySQL counts and Redis Pending.

- [x] **Step 14.2 — Confirm RED**

Run the static harness test. Expected: fail because the script is absent.

- [x] **Step 14.3 — GREEN: implement process-level recovery harness**

Use only disposable task/thread IDs. Do not simulate the kill by throwing inside one Python process. Record Worker 1, Worker 2, node N, checkpoint ID, state version, resume event, per-node counts/events, terminal result, dispatch/audit/mutation counts, elapsed recovery, and Pending.

- [x] **Step 14.4 — Run real acceptance**

Expected final invariants:

```text
same thread_id
same canonical checkpoint at resume
resume starts at N+1
completed nodes before N+1 are not repeated
dispatch rows = 1
audit rows = 1
new shared-memory mutation rows = 0
memory-rain-li
national-102
REROUTE
APPROVED
Pending = 0
```

- [x] **Step 14.5 — Repeatability**

Run the recovery case at least three times with fresh tasks and record every result. A single pass is insufficient evidence for timing-sensitive recovery.

---

## Task 15: Full V1/V2-A/V2-B/V2-C regression and documentation closure

**Files:**

- Modify `README.md`
- Create `docs/verification/v2-c-checkpoint-results.md`
- Update this plan's checkboxes with actual completion state

- [x] **Step 15.1 — Backend quality and unit/integration regression**

Run:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m pytest -q
```

Record the actual test count. The accepted starting baseline is 356 passed plus the real four-store integration test; the final count must be no lower and all new mandatory tests must be present.

- [x] **Step 15.2 — Frontend regression**

Run:

```powershell
Set-Location frontend
npm run lint
npm test -- --run
npm run build
```

Record the actual count. The accepted starting baseline is 36 passed.

- [x] **Step 15.3 — Existing real-store and V2-B regression**

Run the existing real Neo4j graph integration, real four-store shared-memory integration, shared-memory race test, Redis reliability tests, WebSocket E2E, fallback acceptance, and V1 business E2E. Worker recovery must remain <=5 seconds and the accepted Locust hard metrics must remain satisfied.

- [x] **Step 15.4 — V2-C real acceptance**

Run the saver smoke/performance test and the repeated two-worker crash recovery E2E. Verify Docker still reports exactly nine services.

- [x] **Step 15.5 — Preserve accepted business and performance evidence**

Verify the unchanged benchmark artifacts still report Top-1 49/50 (98%), and the core run still reports `memory-rain-li -> national-102 -> REROUTE -> APPROVED`, one dispatch, one audit, and Pending 0. Do not reroute or alter benchmark data to manufacture a pass.

- [x] **Step 15.6 — Scope and secret scans**

Run searches for `update_state`, state mutation routes, pause/resume POST routes, rollback, checkpoint deletion endpoints, target-node override, raw Redis URL logging, Authorization logging, and infrastructure objects in `DispatchGraphState`. Expected: no V2-D behavior and no secret exposure.

- [x] **Step 15.7 — Repository checks required by AGENTS.md**

Run:

```powershell
Set-Location 'C:\Users\24090\OneDrive\Desktop\县域物流识别异常'
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check
git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff -- docs/design.md docs/superpowers/specs/2026-08-27-v2-c-checkpoint-design.md docs/superpowers/plans/2026-08-27-v2-c-checkpoint.md
```

Record only actual output. Do not claim a clean worktree; the repository contains user-owned existing changes.

- [x] **Step 15.8 — Final evidence document**

`docs/verification/v2-c-checkpoint-results.md` must contain:

- exact package and Redis image versions;
- all 19 mandatory test names and pass locations;
- backend/frontend actual counts;
- real saver setup/round-trip result;
- 20-write/20-read minimum/average/P95/maximum and size metrics;
- three real crash-recovery runs;
- service count 9;
- V1/V2-A/V2-B invariant results;
- any blocked evidence stated as blocked, never inferred as passing.

## Mandatory test traceability matrix

| Test | Primary task | Evidence |
| --- | --- | --- |
| `test_thread_registry_create` | 3 | atomic one-task/one-thread row |
| `test_thread_id_stable_across_worker_retry` | 3 | retry reuses identity |
| `test_checkpoint_after_node` | 4 | native post-node snapshot |
| `test_checkpoint_payload_serializable` | 4 | JSON-safe payload |
| `test_checkpoint_excludes_dependencies` | 4 | no infrastructure in state |
| `test_checkpoint_history_append_only` | 3 | immutable metadata history |
| `test_current_checkpoint_pointer` | 3 | MySQL canonical pointer |
| `test_state_version_increments` | 3 | monotonic version |
| `test_terminal_thread_marked` | 3 | idempotent terminal state |
| `test_resume_from_latest_checkpoint` | 8 | exact canonical resume |
| `test_resume_does_not_repeat_completed_nodes` | 8 | N+1 execution |
| `test_resume_no_duplicate_dispatch` | 9 | one dispatch |
| `test_resume_no_duplicate_audit` | 9 | one audit |
| `test_checkpoint_registry_partial_failure` | 6 | Redis orphan, stop next node |
| `test_checkpoint_reconciliation` | 7 | bounded safe promotion |
| `test_thread_read_api` | 11 | authorized current read |
| `test_thread_history_api` | 11 | bounded canonical history |
| `test_production_runtime_api_requires_auth` | 11 | fail-closed production gate |
| `test_checkpoint_event` | 10 | safe committed event |

## Completion gate

V2-C is complete only when every mandatory test is green, the real Redis saver and two-worker resume evidence pass, the service count remains nine, V1/V2-A/V2-B invariants remain green, diff checks pass, and the final scope scan finds no V2-D mutation behavior.

