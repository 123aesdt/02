# CountyFlow V2-D1 Runtime State Override Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an authorized, idempotent `Vehicle.status` override at the exact Environment-to-Capacity stable checkpoint boundary, with official LangGraph state update, MySQL canonical CAS, crash recovery, audit, and real Docker evidence.

**Architecture:** Worker and Override share one short per-thread boundary lease. Worker claims one node at a time with a MySQL `STABLE -> RUNNING` CAS, while Override uses LangGraph 1.2.11 `aupdate_state` on the exact canonical checkpoint and promotes the verified direct successor with a separate override CAS. A durable command ledger and append-only attempts handle retries, partial writes, reconciliation, audit, and idempotency.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, LangGraph 1.2.11, `AsyncRedisSaver`, Redis 8.2.9, SQLAlchemy/Alembic, MySQL 8, pytest/pytest-asyncio, Ruff, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-27-v2-d1-runtime-override-design.md`

## Global constraints

- Do not begin implementation until the user explicitly approves V2-D1 TDD implementation.
- Preserve the eight-agent order and all V1/V2-A/V2-B/V2-C business and recovery results.
- Use the installed `CompiledStateGraph.aupdate_state(config, values, as_node, task_id)` API; never edit Redis saver payloads or keys.
- Implement only `Vehicle.status` at `environment -> capacity`, with `NORMAL -> BROKEN|UNAVAILABLE|MAINTENANCE`.
- Keep Routing unaware of override; it consumes Capacity output.
- Do not write Qdrant, Neo4j, or SharedMemoryFact from runtime override.
- Require production permission `runtime:override`; derive actor identity from the injected authorization provider and fail closed.
- Use exact `expected_version`, old-value, entity-ID, and optional next-node preconditions with no automatic rebase.
- Use `countyflow:lock:thread:{thread_id}`, `SET NX PX`, a random token, and atomic token-safe release.
- Keep Redis-first/MySQL-second ordering and read only the MySQL canonical pointer.
- Keep state typed and JSON serializable; infrastructure dependencies remain outside state.
- The repository currently has staged user-owned files and no `HEAD`; implementation tasks end with diff review gates rather than commits. Do not create a repository history unless the user separately authorizes it.

---

## Planned file map

### New runtime override package

- `backend/app/runtime_overrides/models.py`: enums, immutable commands/results/snapshots, normalized exceptions.
- `backend/app/runtime_overrides/identity.py`: canonical JSON and SHA-256 payload fingerprint.
- `backend/app/runtime_overrides/policy.py`: pure D1 field/transition/boundary policy.
- `backend/app/runtime_overrides/protocols.py`: repository, boundary lease, updater, initializer, and event ports.
- `backend/app/runtime_overrides/redis_lock.py`: per-thread lease and token-safe Lua release.
- `backend/app/runtime_overrides/checkpoint_updater.py`: official `aupdate_state`/`aget_state` adapter.
- `backend/app/runtime_overrides/service.py`: authorized staged override use case.
- `backend/app/runtime_overrides/reconciler.py`: explicit override-orphan recovery.
- `backend/app/runtime_overrides/events.py`: safe idempotent TaskEvent publication.
- `backend/app/runtime_overrides/security.py`: bounded reason/error sanitization.
- `backend/app/runtime_overrides/__init__.py`: narrow public exports.

### Persistence and API

- `backend/app/models/runtime_override.py`: SQLAlchemy command and attempt tables.
- `backend/alembic/versions/20260827_05_runtime_overrides.py`: additive schema and indexes.
- `backend/app/runtime_overrides/sqlalchemy_repository.py`: idempotency reservation, attempts, gate lookup, CAS promotion, history.
- `backend/app/api/v1/runtime_override_schemas.py`: strict request/response models.
- `backend/app/api/v1/runtime_overrides.py`: POST/GET routes and error mapping.

### Existing runtime integration

- `backend/app/runtime_threads/models.py`: override event types and node-claim command.
- `backend/app/runtime_threads/protocols.py`: claim/recovery and authorization context interfaces.
- `backend/app/runtime_threads/sqlalchemy_repository.py`: `STABLE -> RUNNING` claim and stale-worker boundary recovery; cross-table override promotion remains in `RuntimeOverrideRepository`.
- `backend/app/runtime_threads/runner.py`: one-boundary execution and update-checkpoint exclusion.
- `backend/app/runtime_threads/reconciler.py`: preserve node-only orphan rules.
- `backend/app/runtime_threads/auth.py`: read/write permission context.
- `backend/app/workers/dispatch_worker.py`: boundary coordinator loop.
- `backend/app/graph/state.py`: canonical `vehicle_status` field.
- `backend/app/graph/builder.py`: native interrupt boundaries for override-enabled execution.
- `backend/app/agents/capacity.py`: pass canonical status.
- `backend/app/capacity/service.py`: status-based unavailability before existing load rules.
- `backend/app/events/models.py`: override TaskEvent types.
- `backend/app/events/broker.py`: `publish_once` logical idempotency.
- `backend/app/runtime.py`, `backend/app/main.py`, `backend/app/core/config.py`: dependency wiring and fail-closed settings.

### Tests and evidence

- `backend/tests/runtime_overrides/`: domain, policy, repository, service, reconciliation, lock, auth, API, event, and safety tests.
- `backend/tests/runtime_threads/test_boundary_claim.py`: one-node claim/yield behavior.
- `backend/tests/graph/test_capacity_agent.py` and `backend/tests/unit/test_capacity.py`: canonical status integration.
- `backend/tests/integration/test_real_runtime_override.py`: real Redis/MySQL official checkpoint application.
- `backend/tests/integration/test_runtime_override_race.py`: two-client and worker/override races.
- `backend/tests/integration/test_runtime_override_crash.py`: partial promotion and Worker 2 recovery.
- `scripts/verify_v2_d1_runtime_override.py`: 20-run correctness/performance acceptance.
- `docs/verification/v2-d1-runtime-override-results.md`: executed evidence only.
- `docs/verification/raw/v2-d1-runtime-override-performance.json`: raw stage metrics.

## Task 1: Define the typed override domain, fingerprint, and D1 policy

**Files:**

- Create: `backend/app/runtime_overrides/models.py`
- Create: `backend/app/runtime_overrides/identity.py`
- Create: `backend/app/runtime_overrides/policy.py`
- Create: `backend/app/runtime_overrides/protocols.py`
- Create: `backend/app/runtime_overrides/__init__.py`
- Test: `backend/tests/runtime_overrides/test_models.py`
- Test: `backend/tests/runtime_overrides/test_policy.py`
- Test: `backend/tests/runtime_overrides/test_idempotency.py`

**Interfaces:**

- Produces `VehicleRuntimeStatus`, `RuntimeOverrideStatus`, `RuntimeOverrideDecision`, `RuntimeOverrideRequest`, `RuntimeOverrideCommand`, `RuntimeOverrideResult`, `StoredRuntimeOverride`, and normalized domain errors.
- Produces `payload_fingerprint(command) -> str` and `RuntimeOverridePolicy.evaluate(command, thread, state) -> OverridePolicyResult`.

- [ ] **Step 1: Write the failing typed-command and fingerprint tests**

```python
def test_runtime_override_idempotent_replay_fingerprint_is_canonical():
    first = vehicle_status_command(reason="Tyre failure")
    second = vehicle_status_command(reason="Tyre failure")
    assert payload_fingerprint(first) == payload_fingerprint(second)
    assert len(payload_fingerprint(first)) == 64

def test_runtime_override_idempotency_payload_conflict():
    assert payload_fingerprint(vehicle_status_command(new_value="BROKEN")) != payload_fingerprint(
        vehicle_status_command(new_value="MAINTENANCE")
    )
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_models.py backend/tests/runtime_overrides/test_idempotency.py -q`

Expected: FAIL because `app.runtime_overrides` does not exist.

- [ ] **Step 3: Implement immutable models and canonical fingerprinting**

Use `StrEnum`, frozen dataclasses, UTC-aware timestamps, `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, and `hashlib.sha256`. The fingerprint payload contains exactly `thread_id`, entity type/ID, field, old/new value, reason, expected version, and normalized expected next node.

- [ ] **Step 4: Write the failing allowlist tests**

```python
def test_runtime_override_field_allowlist():
    result = policy.evaluate(vehicle_status_command(field="routing_decision"), stable_environment_thread(), normal_state())
    assert (result.decision.value, result.error_code) == ("REJECTED", "OVERRIDE_FIELD_NOT_ALLOWED")

@pytest.mark.parametrize("new_value", ["BROKEN", "UNAVAILABLE", "MAINTENANCE"])
def test_runtime_override_value_validation_accepts_only_d1_transitions(new_value):
    assert policy.evaluate(vehicle_status_command(new_value=new_value), stable_environment_thread(), normal_state()).allowed

def test_runtime_override_value_validation_rejects_recovery():
    result = policy.evaluate(vehicle_status_command(old_value="BROKEN", new_value="NORMAL"), stable_environment_thread(), broken_state())
    assert result.error_code == "OVERRIDE_VALUE_INVALID"
```

- [ ] **Step 5: Run RED, implement the policy table, then run GREEN**

Run RED: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_policy.py -q`

Implement the single registry key `("Vehicle", "status")`, exact entity match, exact `environment -> capacity` boundary, and the three transitions. Run the same command and expect PASS.

- [ ] **Step 6: Run the task gate**

Run: `.venv\Scripts\ruff.exe check backend/app/runtime_overrides backend/tests/runtime_overrides/test_models.py backend/tests/runtime_overrides/test_policy.py backend/tests/runtime_overrides/test_idempotency.py`

Inspect: `git diff -- backend/app/runtime_overrides backend/tests/runtime_overrides`

## Task 2: Add the durable command and append-only attempt ledgers

**Files:**

- Create: `backend/app/models/runtime_override.py`
- Create: `backend/alembic/versions/20260827_05_runtime_overrides.py`
- Create: `backend/app/runtime_overrides/sqlalchemy_repository.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/runtime_overrides/test_sql_models.py`
- Test: `backend/tests/runtime_overrides/test_repository.py`

**Interfaces:**

- Produces `RuntimeOverrideRepository.reserve(command, fingerprint, intent_expires_at) -> StoredRuntimeOverride`.
- Produces `start_attempt`, `attach_result_checkpoint`, `finish_non_applied`, `promote_applied`, `get`, `list_for_thread`, and `has_blocking_intent`.

- [ ] **Step 1: Write the migration/model RED tests**

Assert both tables, all spec columns, globally unique `idempotency_key`, unique `(override_id, attempt_no)`, FK to runtime thread, and the two gate/history indexes.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_sql_models.py -q`

Expected: FAIL because the tables and revision are absent.

- [ ] **Step 3: Add the additive Alembic revision and SQLAlchemy mappings**

Use revision `20260827_05`, down revision `20260827_04`, bounded strings, JSON scalar columns, `DECIMAL(12,3)` timings, timezone-aware datetimes, and no cascade deletion of audit history.

- [ ] **Step 4: Write repository RED tests**

```python
def test_runtime_override_idempotent_replay(repository):
    first = repository.reserve(command, fingerprint, expires_at)
    replay = repository.reserve(command, fingerprint, expires_at)
    assert replay.override_id == first.override_id
    assert repository.count_commands() == 1

def test_runtime_override_idempotency_payload_conflict(repository):
    repository.reserve(command, fingerprint, expires_at)
    with pytest.raises(RuntimeOverrideIdempotencyConflict):
        repository.reserve(changed_command_same_key, changed_fingerprint, expires_at)
```

- [ ] **Step 5: Implement transactional reservation and immutable attempts**

Use the globally unique idempotency-key constraint as the final concurrency guard. Catch `IntegrityError`, reload by key, require both actor and fingerprint to match, and either return the stored command or raise the normalized conflict. Attempt numbers use a transaction-protected maximum plus unique constraint; retries append rather than update previous attempts.

- [ ] **Step 6: Implement override-specific promotion CAS**

`promote_applied` must require exact thread ID, status `STABLE`, source checkpoint, expected state version, current/next node, and override status `APPLYING|PARTIAL`. In one transaction it sets the result pointer, increments `state_version`, leaves `checkpoint_count` unchanged, finalizes command/attempt, and appends the unique runtime event.

- [ ] **Step 7: Run GREEN and inspect migration**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_sql_models.py backend/tests/runtime_overrides/test_repository.py -q`

Run: `.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head`

Inspect: `git diff -- backend/alembic/versions/20260827_05_runtime_overrides.py backend/app/models/runtime_override.py backend/app/runtime_overrides/sqlalchemy_repository.py`

## Task 3: Implement the shared per-thread boundary lease

**Files:**

- Create: `backend/app/runtime_overrides/redis_lock.py`
- Test: `backend/tests/runtime_overrides/test_runtime_override_thread_lock.py`
- Test: `backend/tests/integration/test_real_runtime_override_lock.py`

**Interfaces:**

- Produces `RuntimeBoundaryLease.acquire(thread_id) -> BoundaryLeaseHandle` and `release(handle) -> bool`.
- Lock key is exactly `countyflow:lock:thread:{thread_id}`.

- [ ] **Step 1: Write token ownership RED tests**

```python
async def test_runtime_override_thread_lock(lock, redis):
    first = await lock.acquire(THREAD_ID)
    second = await lock.acquire(THREAD_ID)
    assert first.acquired is True
    assert second.acquired is False
    assert await lock.release(first) is True

async def test_foreign_token_cannot_release(lock, redis):
    handle = await lock.acquire(THREAD_ID)
    assert await lock.release(handle.with_token("foreign")) is False
    assert await redis.exists(handle.key) == 1
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_thread_lock.py -q`

- [ ] **Step 3: Implement `SET NX PX` and Lua compare-delete**

Normalize Redis errors to `RuntimeBoundaryLeaseUnavailable` without embedding connection strings. Validate positive TTL in the constructor. Do not import or reuse the memory mutation lock namespace.

- [ ] **Step 4: Run GREEN and real Redis proof**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_thread_lock.py backend/tests/integration/test_real_runtime_override_lock.py -q`

Inspect: `git diff -- backend/app/runtime_overrides/redis_lock.py backend/tests/runtime_overrides/test_runtime_override_thread_lock.py`

## Task 4: Extend authorization without trusting request data

**Files:**

- Modify: `backend/app/runtime_threads/auth.py`
- Modify: `backend/app/runtime_threads/protocols.py`
- Modify: `backend/app/runtime_threads/service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/runtime_overrides/test_runtime_override_auth_required.py`
- Test: `backend/tests/api/test_runtime_threads.py`

**Interfaces:**

- Produces `RuntimeAuthorizationContext(operator_id, role, permissions)`.
- Produces `authorize_read(...) -> RuntimeAuthorizationContext` and `authorize_override(...) -> RuntimeAuthorizationContext`.

- [ ] **Step 1: Write auth RED tests**

```python
def test_runtime_override_auth_required(disabled_authorizer):
    with pytest.raises(RuntimeThreadAuthorizationError):
        disabled_authorizer.authorize_override(thread_id=THREAD_ID, task_id=TASK_ID)

def test_human_confirmed_is_not_an_authorization_field():
    assert "human_confirmed" not in CreateRuntimeOverrideRequest.model_fields
    assert "operator_id" not in CreateRuntimeOverrideRequest.model_fields
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_auth_required.py backend/tests/api/test_runtime_threads.py -q`

- [ ] **Step 3: Implement context-returning adapters and fail-closed wiring**

Trusted test/development context contains explicit `runtime:read` and `runtime:override`. Disabled raises for both. External injection remains mandatory when production runtime writes are enabled. Preserve current read endpoint results.

- [ ] **Step 4: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_auth_required.py backend/tests/api/test_runtime_threads.py backend/tests/runtime_threads/test_service.py -q`

Inspect: `git diff -- backend/app/runtime_threads/auth.py backend/app/runtime_threads/protocols.py backend/app/main.py`

## Task 5: Make Worker boundary ownership real before adding writes

**Files:**

- Modify: `backend/app/runtime_threads/models.py`
- Modify: `backend/app/runtime_threads/protocols.py`
- Modify: `backend/app/runtime_threads/sqlalchemy_repository.py`
- Modify: `backend/app/runtime_threads/runner.py`
- Modify: `backend/app/runtime_threads/reconciler.py`
- Modify: `backend/app/graph/builder.py`
- Modify: `backend/app/workers/dispatch_worker.py`
- Modify: `backend/app/runtime.py`
- Test: `backend/tests/runtime_threads/test_boundary_claim.py`
- Test: `backend/tests/runtime_threads/test_graph_checkpointing.py`
- Test: `backend/tests/workers/test_dispatch_worker.py`

**Interfaces:**

- Produces `RuntimeThreadRepository.claim_next_node(thread_id, expected_checkpoint_id, expected_state_version, expected_next_node, worker_consumer) -> RuntimeThreadSnapshot`.
- Produces `CheckpointedGraphRunner.run_one_boundary(thread, graph_input=None, resume_key=None) -> BoundaryRunResult`.
- Worker and Override consume the same `RuntimeBoundaryLease`.

- [ ] **Step 1: Write the worker claim race RED test**

```python
async def test_worker_claim_changes_stable_to_running_before_capacity(repository, coordinator):
    thread = stable_environment_thread(version=7)
    claimed = await coordinator.claim(thread)
    assert claimed.status.value == "RUNNING"
    with pytest.raises(ThreadNotStable):
        repository.claim_next_node(THREAD_ID, SOURCE_CP, 7, "capacity", "worker-2")
```

- [ ] **Step 2: Write one-node execution RED tests**

Prove a call from Environment executes Capacity exactly once, returns at the Capacity boundary, promotes the Capacity checkpoint, and does not start Routing. Prove the worker reloads pointer/version before every claim.

- [ ] **Step 3: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_threads/test_boundary_claim.py backend/tests/runtime_threads/test_graph_checkpointing.py backend/tests/workers/test_dispatch_worker.py -q`

- [ ] **Step 4: Implement claim CAS and native all-node interrupt boundaries**

Create new rows as `STABLE` with `next_node=intake`. Compile override-enabled worker graphs with `interrupt_after=list(NODE_ORDER[:-1])`. Split runner execution into one boundary per invocation. Keep Redis checkpoint persistence and MySQL promotion unchanged for normal nodes.

- [ ] **Step 5: Add durable pause boundaries and the single-winner Worker/Override CAS**

Under the boundary lease, reload the thread and call `has_blocking_intent`. Yield on an unexpired matching `PENDING` intent or any matching `APPLYING`/`PARTIAL` operation; otherwise claim the exact node, release the lease, and execute. A worker never holds the lease during node code. A stale `RUNNING` reclaim remains under the existing dispatch execution lock and exact canonical resume rules.

- [ ] **Step 6: Run GREEN and V2-C resume regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_threads backend/tests/workers/test_dispatch_worker.py -q`

Inspect: `git diff -- backend/app/runtime_threads backend/app/workers/dispatch_worker.py backend/app/graph/builder.py`

## Task 6: Add canonical vehicle status and make Capacity consume it

**Files:**

- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/agents/capacity.py`
- Modify: `backend/app/capacity/service.py`
- Modify: `backend/app/runtime.py`
- Create: `backend/app/runtime_overrides/state_initializer.py`
- Test: `backend/tests/graph/test_capacity_agent.py`
- Test: `backend/tests/unit/test_capacity.py`
- Test: `backend/tests/runtime_overrides/test_state_initializer.py`

**Interfaces:**

- Produces `RuntimeStateInitializer.initialize(task) -> DispatchGraphState` with server-derived `vehicle_status`.
- Extends `CapacityService.evaluate(..., *, vehicle_status: VehicleRuntimeStatus) -> CapacityResult`.

- [ ] **Step 1: Write canonical-state and Capacity RED tests**

```python
async def test_broken_vehicle_excluded_by_capacity(capacity_service):
    result = await capacity_service.evaluate("driver-li", "vehicle-001", "route-1", 1, vehicle_status="BROKEN")
    assert result.vehicle_available is False
    assert result.capacity_status == "UNAVAILABLE"

async def test_capacity_agent_reads_canonical_vehicle_status():
    patch = await capacity_node(state(vehicle_status="MAINTENANCE"), service)
    assert patch["capacity_state"]["vehicle_available"] is False
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/test_capacity.py backend/tests/graph/test_capacity_agent.py backend/tests/runtime_overrides/test_state_initializer.py -q`

- [ ] **Step 3: Implement the status field and initializer port**

Use the literal enum from Task 1. Resolve initial status through an injected server-side application port; the Docker adapter maps the accepted `vehicle-001` operational snapshot to `NORMAL`. Do not add the field to the external task POST body.

- [ ] **Step 4: Implement minimal Capacity precedence**

Return unavailable immediately for `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE`; for `NORMAL`, execute the existing provider and threshold logic unchanged. Do not modify Routing.

- [ ] **Step 5: Run GREEN and routing regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/test_capacity.py backend/tests/graph/test_capacity_agent.py backend/tests/graph/test_routing_agent.py -q`

Inspect: `git diff -- backend/app/graph/state.py backend/app/agents/capacity.py backend/app/capacity/service.py`

## Task 7: Implement the official checkpoint updater and successful service path

**Files:**

- Create: `backend/app/runtime_overrides/checkpoint_updater.py`
- Create: `backend/app/runtime_overrides/service.py`
- Modify: `backend/app/runtime_overrides/protocols.py`
- Test: `backend/tests/runtime_overrides/test_checkpoint_updater.py`
- Test: `backend/tests/runtime_overrides/test_service.py`

**Interfaces:**

- Produces `LangGraphStateUpdater.update(source, patch, as_node, override_id) -> UpdatedCheckpoint`.
- Produces `RuntimeOverrideService.apply(thread_id: str, request: RuntimeOverrideRequest) -> RuntimeOverrideResult`; the service authorizes, derives the actor, and constructs the immutable command.

- [ ] **Step 1: Write the installed-API RED test**

```python
async def test_runtime_override_updates_checkpoint(compiled_graph, source_record):
    updated = await updater.update(source_record, {"vehicle_status": "BROKEN"}, as_node="environment", override_id=OVERRIDE_ID)
    assert updated.parent_checkpoint_id == source_record.checkpoint_id
    assert updated.next_nodes == ("capacity",)
    assert updated.state["vehicle_status"] == "BROKEN"
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_checkpoint_updater.py -q`

- [ ] **Step 3: Implement only the official adapter**

Call `graph.aupdate_state(source.config, patch, as_node=as_node, task_id=override_id)`, then `graph.aget_state(result_config)` and `checkpoint_store.get_exact` for the returned checkpoint ID. Validate direct parent, namespace, next tuple, unchanged node/count, exact state diff, JSON encoding, and byte limit.

- [ ] **Step 4: Write service RED tests**

```python
async def test_runtime_override_success(service):
    result = await service.apply(THREAD_ID, vehicle_status_request(expected_version=7))
    assert (result.status.value, result.before_version, result.after_version) == ("APPLIED", 7, 8)

async def test_runtime_override_state_version_increment(service, repository):
    await service.apply(THREAD_ID, vehicle_status_request(expected_version=7))
    thread = repository.get_by_thread_id(THREAD_ID)
    assert thread.state_version == 8
    assert thread.checkpoint_count == 4
```

- [ ] **Step 5: Implement authorization, reservation, lease, validation, update, and promotion sequence**

Use one immediate lease attempt and an after-lock thread reload. Always release in `finally`. Store `result_checkpoint_id` before promotion. Map domain rejections to stored final results. Never catch `CancelledError` as a normal failure.

- [ ] **Step 6: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_checkpoint_updater.py backend/tests/runtime_overrides/test_service.py -q`

Inspect: `git diff -- backend/app/runtime_overrides/checkpoint_updater.py backend/app/runtime_overrides/service.py`

## Task 8: Cover all preconditions, failure stages, and explicit reconciliation

**Files:**

- Create: `backend/app/runtime_overrides/reconciler.py`
- Modify: `backend/app/runtime_overrides/service.py`
- Modify: `backend/app/runtime_threads/reconciler.py`
- Test: `backend/tests/runtime_overrides/test_service_failures.py`
- Test: `backend/tests/runtime_overrides/test_reconciliation.py`

**Interfaces:**

- Produces `RuntimeOverrideReconciler.reconcile(override_id) -> RuntimeOverrideResult`.
- Generic `ThreadCheckpointReconciler` continues to accept only completed-node checkpoint candidates.

- [ ] **Step 1: Write the mandatory rejection RED cases**

Add exact tests named:

```text
test_runtime_override_expected_version_conflict
test_runtime_override_old_value_precondition
test_runtime_override_terminal_rejected
test_runtime_override_not_stable_rejected
test_runtime_override_checkpoint_write_failure
test_runtime_override_promotion_failure
test_runtime_override_orphan_not_canonical
```

Assert exact safe code, final ledger status, unchanged canonical pointer/version, and whether worker gating remains active.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_service_failures.py -q`

- [ ] **Step 3: Implement failure-state transitions**

Checkpoint write failure becomes `FAILED` and unblocks the worker. A recorded result with transient promotion failure becomes `PARTIAL` and blocks. A CAS observation showing a newer pointer/version becomes `CONFLICT`. An unidentified update checkpoint is never selected.

- [ ] **Step 4: Write reconciliation RED tests**

```python
async def test_runtime_override_reconciliation(reconciler, partial_override):
    result = await reconciler.reconcile(partial_override.override_id)
    assert (result.status.value, result.after_version) == ("APPLIED", 8)

async def test_runtime_override_reconcile_conflict(reconciler, advanced_thread):
    result = await reconciler.reconcile(PARTIAL_OVERRIDE_ID)
    assert result.status.value == "CONFLICT"
    assert advanced_thread.current_checkpoint_id != RESULT_CP
```

- [ ] **Step 5: Implement exact-ID reconciliation and generic exclusion**

Require stored source/result IDs and exact direct ancestry. Do not call `list_bounded` to select a candidate. Ensure the generic reconciler cannot classify `metadata.source == "update"` or unchanged completed-node count as a normal node checkpoint.

- [ ] **Step 6: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_service_failures.py backend/tests/runtime_overrides/test_reconciliation.py backend/tests/runtime_threads/test_consistency.py -q`

Inspect: `git diff -- backend/app/runtime_overrides/reconciler.py backend/app/runtime_threads/reconciler.py`

## Task 9: Add durable audit and idempotent safe events

**Files:**

- Create: `backend/app/runtime_overrides/events.py`
- Create: `backend/app/runtime_overrides/security.py`
- Modify: `backend/app/events/models.py`
- Modify: `backend/app/events/broker.py`
- Modify: `backend/app/runtime_threads/models.py`
- Test: `backend/tests/runtime_overrides/test_runtime_override_audit.py`
- Test: `backend/tests/runtime_overrides/test_runtime_override_event.py`
- Test: `backend/tests/runtime_overrides/test_runtime_override_secret_safety.py`
- Test: `backend/tests/api/test_redis_task_event_broker.py`

**Interfaces:**

- Extends `TaskEventBroker.publish_once(event_key, event) -> TaskEvent`.
- Produces `RuntimeOverrideEventPublisher.requested(result)` and `terminal(result)`.

- [ ] **Step 1: Write audit/event/safety RED tests**

Assert all actor/checkpoint/version/entity/reason fields exist in MySQL, a replay produces one logical requested and one logical terminal event, and Bearer/API-key/password/Redis-URL material is absent from reason, error summary, event, and logs.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_audit.py backend/tests/runtime_overrides/test_runtime_override_event.py backend/tests/runtime_overrides/test_runtime_override_secret_safety.py -q`

- [ ] **Step 3: Implement event enums, sanitization, and Redis atomic publish-once**

Use deterministic keys `runtime-override:{override_id}:requested` and `runtime-override:{override_id}:{final_status}`. A Lua script checks the marker, increments sequence, XADDs, stores the event ID, and returns it atomically. Implement equivalent in-memory behavior for tests.

- [ ] **Step 4: Run GREEN and existing broker regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_runtime_override_audit.py backend/tests/runtime_overrides/test_runtime_override_event.py backend/tests/runtime_overrides/test_runtime_override_secret_safety.py backend/tests/api/test_redis_task_event_broker.py backend/tests/api/test_task_events.py -q`

Inspect: `git diff -- backend/app/events backend/app/runtime_overrides/events.py backend/app/runtime_overrides/security.py`

## Task 10: Expose strict POST and safe GET APIs

**Files:**

- Create: `backend/app/api/v1/runtime_override_schemas.py`
- Create: `backend/app/api/v1/runtime_overrides.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.docker.env.example`
- Test: `backend/tests/api/test_runtime_overrides.py`
- Test: `backend/tests/config/test_settings.py`

**Interfaces:**

- Adds the three routes in the design and strict `extra="forbid"` request models.
- Adds `runtime_override_api_enabled`, `runtime_override_lock_ttl_ms=10000`, and external authorization validation.

- [ ] **Step 1: Write API RED tests**

Cover 201 create, 200 replay, bounded safe response, 403, both 404s, all specified 409 codes, both 422 codes, and 503. Assert body-supplied `operator_id`, `human_confirmed`, `checkpoint_id`, `target_node`, JSON path, or whole state produces schema rejection.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/api/test_runtime_overrides.py backend/tests/config/test_settings.py -q`

- [ ] **Step 3: Implement schemas, thin route mapping, and wiring**

Create the command only after authorization context is available. Return 201 only for first successful creation and 200 for stored replay. GET history clamps limit to the configured maximum. Do not return full state or permission sets.

- [ ] **Step 4: Implement production configuration failure**

Production rejects `runtime_override_api_enabled=true` unless the runtime authorization provider is `external` and an implementation is injected. Override enablement also requires official checkpointing and boundary-stepped worker execution.

- [ ] **Step 5: Run GREEN and V2-C read API regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/api/test_runtime_overrides.py backend/tests/api/test_runtime_threads.py backend/tests/config/test_settings.py -q`

Inspect: `git diff -- backend/app/api/v1/runtime_overrides.py backend/app/api/v1/runtime_override_schemas.py backend/app/main.py backend/app/core/config.py`

## Task 11: Prove next-node visibility and both concurrency races

**Files:**

- Create: `backend/tests/runtime_overrides/test_next_node_visibility.py`
- Create: `backend/tests/integration/test_runtime_override_race.py`
- Modify: `backend/tests/runtime_overrides/service_fakes.py`

**Interfaces:**

- Uses the production service, boundary coordinator, repository, and updater through fake and real adapters; no test-only production branch.

- [ ] **Step 1: Write next-node visibility RED test**

```python
async def test_runtime_override_next_node_reads_new_value(harness):
    await harness.pause_after_environment(vehicle_status="NORMAL", state_version=7)
    applied = await harness.override(new_value="BROKEN", expected_version=7)
    await harness.resume_one_boundary()
    assert applied.status.value == "APPLIED"
    assert harness.capacity_invocations == 1
    assert harness.capacity_seen_statuses == ["BROKEN"]
```

- [ ] **Step 2: Write worker/override ownership RED test**

Use barriers at the lease and `claim_next_node` boundaries. Prove exactly two allowed outcomes: Override wins and Capacity sees `BROKEN`, or Worker wins and Override returns `THREAD_NOT_STABLE`; reject any trace with `APPLIED` plus `NORMAL`.

- [ ] **Step 3: Write two-client RED test**

Create `test_runtime_override_concurrent_race`. Two independent sessions submit version 7 transitions to `BROKEN` and `MAINTENANCE`. Assert exactly one `APPLIED`, the other busy/version conflict, final version 8, one override checkpoint, and one applied logical event.

- [ ] **Step 4: Run RED, fix only orchestration defects, then run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/runtime_overrides/test_next_node_visibility.py backend/tests/integration/test_runtime_override_race.py -q`

Expected final result: PASS without weakening barriers or accepting a third outcome.

- [ ] **Step 5: Inspect the race-sensitive diff**

Inspect: `git diff -- backend/app/runtime_threads backend/app/runtime_overrides backend/app/workers/dispatch_worker.py backend/tests/integration/test_runtime_override_race.py`

## Task 12: Prove real partial recovery, worker crash recovery, and 20/20 acceptance

**Files:**

- Create: `backend/tests/integration/test_real_runtime_override.py`
- Create: `backend/tests/integration/test_runtime_override_crash.py`
- Create: `scripts/verify_v2_d1_runtime_override.py`
- Create: `docs/verification/raw/v2-d1-runtime-override-performance.json`

**Interfaces:**

- The script emits machine-readable per-run stage timings and a summary with min/avg/p95/max and TTL inequality.

- [ ] **Step 1: Write the real official-checkpoint RED scenario**

Against Docker Redis/MySQL, create an Environment checkpoint at version 7 with `vehicle_status=NORMAL`, call the real service, exact-read the returned checkpoint, resume Capacity once, and assert version 8, `BROKEN`, unavailable capacity, and no use of Vehicle A by Routing.

- [ ] **Step 2: Write the crash-window RED scenario**

Inject process failure after official Redis update and result-ID persistence but before promotion. Assert current read remains V7, result is not canonical, worker claim is blocked, reconciliation promotes only that result to V8, and then resume is allowed.

- [ ] **Step 3: Write the worker-crash RED scenario**

Stop Worker 1 after Environment promotion, apply override through Backend, start/allow Worker 2 to `XAUTOCLAIM`, and assert recovery remains at or below five seconds and Capacity reads `BROKEN` exactly once.

- [ ] **Step 4: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/integration/test_real_runtime_override.py backend/tests/integration/test_runtime_override_crash.py -q`

- [ ] **Step 5: Complete Docker wiring and run GREEN**

Run the same command until PASS using the production adapters. Do not replace Redis/MySQL with fakes in these tests.

- [ ] **Step 6: Run 20 legal overrides and record performance**

Run: `.venv\Scripts\python.exe scripts/verify_v2_d1_runtime_override.py --runs 20 --output docs/verification/raw/v2-d1-runtime-override-performance.json`

Expected: `20/20 APPLIED`, `20/20 Capacity saw new state`, no duplicate checkpoint/version/event, and `ttl_ms > max(p99_override_ms, p99_boundary_claim_ms) + 2000`.

- [ ] **Step 7: Inspect evidence**

Inspect: `Get-Content docs/verification/raw/v2-d1-runtime-override-performance.json`

Do not write claimed metrics into the verification summary until this command has actually completed.

## Task 13: Run full regression and close documentation

**Files:**

- Modify: `docs/design.md` only if implementation evidence changes an already selected value such as measured TTL.
- Create: `docs/verification/v2-d1-runtime-override-results.md`

**Interfaces:**

- Produces the final evidence report with exact command output, service health, business result, race/crash outcomes, 20-run metrics, and deferred scope.

- [ ] **Step 1: Run backend lint and full tests**

Run: `.venv\Scripts\ruff.exe check backend`

Run: `.venv\Scripts\python.exe -m pytest backend -q`

Record exact totals and skips.

- [ ] **Step 2: Run frontend regression**

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend test -- --run`

Run: `npm --prefix frontend run build`

No D1 action UI is expected.

- [ ] **Step 3: Run real Docker dependency and E2E suites**

Run the project's existing real MySQL, Redis Streams/checkpoint, Qdrant, Neo4j, two-worker recovery, and Docker E2E commands documented in `docs/verification/v2-c-checkpoint-results.md`, followed by Tasks 11-12's new real suites.

Confirm all nine services healthy, Redis Pending `0`, worker recovery <=5 seconds, and `memory-rain-li -> national-102 -> REROUTE -> APPROVED` with one dispatch and one audit.

- [ ] **Step 4: Write only observed evidence**

The report must include exact commands, exit status, test totals, three recovery durations, 20-run correctness totals, stage min/avg/p95/max, TTL formula outcome, concurrent winner/loser statuses, partial recovery outcome, and any skips with reasons.

- [ ] **Step 5: Run design and placeholder scans**

Run: `rg -n "arbitrary JSON|direct.*Redis.*checkpoint|goto|terminal reopen|Qdrant.*write|Neo4j.*write" docs/superpowers/specs/2026-08-27-v2-d1-runtime-override-design.md docs/superpowers/plans/2026-08-27-v2-d1-runtime-override.md`

Review every match to confirm it is an explicit prohibition or deferral.

- [ ] **Step 6: Run the final repository gate**

Run: `git -c safe.directory="C:/Users/24090/OneDrive/Desktop/县域物流识别异常" diff --check`

Inspect: `git status --short`

Do not commit staged or untracked user-owned work.

## Mandatory test traceability matrix

| Required test | Planned file/task |
| --- | --- |
| `test_runtime_override_success` | `test_service.py`, Task 7 |
| `test_runtime_override_updates_checkpoint` | `test_checkpoint_updater.py`, Task 7 |
| `test_runtime_override_state_version_increment` | `test_service.py`, Task 7 |
| `test_runtime_override_next_node_reads_new_value` | `test_next_node_visibility.py`, Task 11 |
| `test_broken_vehicle_excluded_by_capacity` | `test_capacity.py`, Task 6 |
| `test_runtime_override_expected_version_conflict` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_old_value_precondition` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_field_allowlist` | `test_policy.py`, Task 1 |
| `test_runtime_override_value_validation` | `test_policy.py`, Task 1 |
| `test_runtime_override_terminal_rejected` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_not_stable_rejected` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_thread_lock` | `test_runtime_override_thread_lock.py`, Task 3 |
| `test_runtime_override_concurrent_race` | `test_runtime_override_race.py`, Task 11 |
| `test_runtime_override_idempotent_replay` | `test_repository.py` and `test_service.py`, Tasks 2 and 7 |
| `test_runtime_override_idempotency_payload_conflict` | `test_idempotency.py` and `test_repository.py`, Tasks 1 and 2 |
| `test_runtime_override_checkpoint_write_failure` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_promotion_failure` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_orphan_not_canonical` | `test_service_failures.py`, Task 8 |
| `test_runtime_override_reconciliation` | `test_reconciliation.py`, Task 8 |
| `test_runtime_override_reconcile_conflict` | `test_reconciliation.py`, Task 8 |
| `test_runtime_override_audit` | `test_runtime_override_audit.py`, Task 9 |
| `test_runtime_override_event` | `test_runtime_override_event.py`, Task 9 |
| `test_runtime_override_auth_required` | `test_runtime_override_auth_required.py`, Task 4 |
| `test_runtime_override_secret_safety` | `test_runtime_override_secret_safety.py`, Task 9 |

## Completion gate

V2-D1 implementation is complete only when all mandatory tests pass, the real Environment-to-Capacity example proves exact next-node visibility, the two race suites permit only the two safe outcomes, partial recovery never exposes an orphan, 20/20 real legal overrides succeed, all stage metrics are recorded, the TTL inequality passes, Worker recovery remains <=5 seconds, the nine-service business E2E remains unchanged, frontend regression passes, Pending is `0`, and `git diff --check` is clean.
