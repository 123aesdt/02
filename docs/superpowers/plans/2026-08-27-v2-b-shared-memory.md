# CountyFlow V2-B Shared Memory Mutation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an effectively consistent, auditable DispatchMemory mutation control plane across MySQL, Redis, Qdrant, and Neo4j without changing the existing eight-agent runtime or V1/V2-A read decisions.

**Architecture:** `SharedMemoryMutationService` validates and canonicalizes a command, takes a fact-level Redis lock, evaluates an immutable MySQL mutation ledger against an optimistically locked canonical fact, and applies idempotent Qdrant/Neo4j projections. Partial work remains recoverable through `MemoryMutationReconciler`; MySQL remains authoritative and no distributed transaction is claimed.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, Alembic, MySQL 8.4, Redis 7.4, Qdrant, Neo4j 5.26 Community, pytest, React/TypeScript/Vitest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-27-v2-b-shared-memory-design.md`

## Global Constraints

- Implement only `DispatchMemory`; enum-only `ChatMemory`, `LLMWiki`, and `CodeGraph` must be rejected by the application service.
- Do not change `DispatchGraphState`, LangGraph checkpoints, running thread state, target nodes, or the eight-agent topology.
- Do not add 2PC, XA, Seata, Temporal, Saga frameworks, Kafka, another broker, an automatic scheduler, or lock renewal.
- MySQL is control truth; Redis is only a lock; Qdrant and Neo4j are retryable projections using the MySQL control version.
- Use `Decimal`/`NUMERIC(5,4)` for confidence and SQLAlchemy `version_id_col` for fact concurrency.
- Use SHA-256 over canonical UTF-8 JSON; never use Python `hash()` or accidental dict iteration order.
- Preserve V1 Qdrant ranking/adoption and V2-A allowlists, Cypher parameterization, hop/result bounds, and safe degradation.
- Preserve the accepted Qdrant Top-1 98% benchmark evidence; V2-B must not alter the benchmark dataset or scoring rule to manufacture a pass.
- `MEMORY_AUTO_APPLY_MIN_CONFIDENCE=0.75`, `MEMORY_LOWER_CONFIDENCE_REJECT_DELTA=0.15`, `MEMORY_MUTATION_TIMEOUT_SECONDS=5.0`, and `MEMORY_MUTATION_LOCK_TTL_MS=10000` are docker-dev/test configuration, not logistics truths.
- Do not persist secrets, Authorization headers, raw embeddings, provider request dumps, or infrastructure objects.
- The repository currently has no commits and contains user-owned staged/untracked work. Do not stage or commit unless the user explicitly authorizes it; use `git diff` checkpoints.

## File Structure

- `backend/app/shared_memory/models.py`: frozen command/result/domain enums and typed errors.
- `backend/app/shared_memory/identity.py`: canonical JSON, fact/content/payload/evidence fingerprints.
- `backend/app/shared_memory/policy.py`: pure deterministic decision matrix.
- `backend/app/shared_memory/protocols.py`: repository, lock, projection, event, and clock ports.
- `backend/app/shared_memory/sqlalchemy_repository.py`: MySQL control-plane transactions and optimistic-lock translation.
- `backend/app/shared_memory/redis_lock.py`: independent fact-level token-safe lock.
- `backend/app/shared_memory/qdrant_projection.py`: deterministic versioned vector projection adapter.
- `backend/app/shared_memory/neo4j_projection.py`: allowlisted, parameterized graph projection adapter.
- `backend/app/shared_memory/service.py`: orchestration and idempotent terminal results.
- `backend/app/shared_memory/reconciler.py`: explicit resume path for PENDING/PARTIAL mutations.
- `backend/app/shared_memory/events.py`: adapter to the existing event broker.
- `backend/app/models/shared_memory.py`: SQLAlchemy fact, mutation, evidence, and attempt rows.
- `backend/app/api/v1/memory_schemas.py`: request/response models.
- `backend/app/api/v1/memory_mutations.py`: internal/management endpoints.
- `backend/alembic/versions/20260827_03_shared_memory_control_plane.py`: additive schema migration.
- `frontend/src/types/memory.ts`, `frontend/src/services/api/memory-client.ts`: typed API boundary.
- `frontend/src/pages/memory-page.tsx`: minimal current fact/history display; disabled approval action.
- `scripts/shared_memory_integration.py`, `scripts/test-shared-memory.ps1`: real Redis/MySQL/Qdrant/Neo4j acceptance.

---

### Task 1: Domain types and deterministic identity

**Files:**
- Create: `backend/app/shared_memory/__init__.py`
- Create: `backend/app/shared_memory/models.py`
- Create: `backend/app/shared_memory/identity.py`
- Test: `backend/tests/shared_memory/test_identity.py`
- Test: `backend/tests/shared_memory/test_models.py`

**Interfaces:**
- Produces: `MemoryCategory`, `MemoryFactKind`, `MemoryTarget`, `MemoryFactStatus`, `MutationDecision`, `MutationStatus` (including FINALIZING), `ProjectionStatus` (NOT_REQUIRED/PENDING/STAGED/ACTIVE/RETIRED/FAILED), `SharedMemoryMutationCommand`, `MemoryMutationResult`.
- Produces: `canonical_json(value: object) -> str`, `build_fact_key(command) -> str`, `content_fingerprint(command) -> str`, `payload_fingerprint(command) -> str`, `evidence_fingerprint(command) -> str`.

- [ ] **Step 1: Write failing identity and serialization tests**

```python
def test_attribute_fact_key_is_stable_across_value_change():
    normal = command(value={"status": "Normal"})
    broken = command(value={"status": "Broken"})
    assert build_fact_key(normal) == build_fact_key(broken)
    assert content_fingerprint(normal) != content_fingerprint(broken)

def test_payload_fingerprint_is_order_independent():
    left = command(value={"b": 2, "a": 1})
    right = command(value={"a": 1, "b": 2})
    assert payload_fingerprint(left) == payload_fingerprint(right)
```

- [ ] **Step 2: Run RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_identity.py tests/shared_memory/test_models.py -q`

Expected: collection fails because `app.shared_memory` does not exist.

- [ ] **Step 3: Implement frozen JSON-serializable contracts and SHA-256 identity**

```python
def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def build_fact_key(command: SharedMemoryMutationCommand) -> str:
    identity = command.fact_identity()
    return f"smf_{_digest(identity)}"
```

Validate bounded IDs, confidence in `[0,1]`, UTC-aware incoming/expiry timestamps, evidence presence, JSON serialization, and target registry compatibility. Reject non-Dispatch categories at the service boundary, not while constructing enum values.

Add boundary tests for 16 KiB canonical `value_json`, 32 KiB `proposed_fact_json`, 2,000-character evidence text, 512-character reason/reference/summary, naive timestamps, and non-finite numeric values.

- [ ] **Step 4: Run GREEN and inspect diff**

Run the focused pytest command from Step 2, then `git diff -- backend/app/shared_memory backend/tests/shared_memory`.

Expected: identity/model tests pass; no production infrastructure imports appear in domain files.

---

### Task 2: Pure conflict and merge policy

**Files:**
- Create: `backend/app/shared_memory/policy.py`
- Test: `backend/tests/shared_memory/test_policy.py`

**Interfaces:**
- Consumes: `SharedMemoryMutationCommand`, current `SharedMemoryFactSnapshot | None`, identity fingerprints, `MemoryPolicySettings`.
- Produces: `MemoryDecision(decision, reason_code, before_version, after_version, proposed_status, requires_projection)`.

- [ ] **Step 1: Write one behavior test per required decision**

```python
@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("missing", MutationDecision.CREATE),
        ("duplicate", MutationDecision.NOOP),
        ("new_evidence", MutationDecision.MERGE),
        ("expired", MutationDecision.REPLACE),
        ("human_confirmed_conflict", MutationDecision.REPLACE),
        ("stale_conflict", MutationDecision.REJECT),
        ("lower_confidence_conflict", MutationDecision.REJECT),
        ("unconfirmed_conflict", MutationDecision.CONFLICT_REVIEW),
        ("low_confidence", MutationDecision.CONFLICT_REVIEW),
    ],
)
def test_policy_matrix(scenario, expected):
    assert evaluate(scenario).decision == expected
```

Add explicit tests named `test_memory_create`, `test_memory_duplicate_noop`, `test_memory_merge_evidence`, `test_memory_replace_expired`, `test_memory_human_confirmed_replace`, `test_memory_stale_reject`, `test_memory_lower_confidence_reject`, `test_memory_conflict_requires_review`, `test_memory_low_confidence_requires_review`, and `test_memory_expiry`.

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_policy.py -q`

Expected: import or missing `evaluate_mutation` failures.

- [ ] **Step 3: Implement the exact ordered policy from the spec**

```python
def evaluate_mutation(current, command, settings, *, now):
    if command.expected_version != expected_version(current):
        raise MemoryVersionConflict(command.fact_key, command.expected_version, expected_version(current))
    if command.confidence < settings.auto_apply_min_confidence and not command.human_confirmed:
        return conflict_review(current)
    if current is None:
        return create_version_one()
    if current.is_expired(now):
        return replace(current)
    if command.content_fingerprint == current.content_fingerprint:
        return noop(current) if evidence_is_duplicate(current, command) else merge(current)
    if command.human_confirmed:
        return replace(current)
    if command.incoming_timestamp < current.updated_at:
        return reject("STALE_EVIDENCE")
    if current.confidence - command.confidence >= settings.lower_confidence_reject_delta:
        return reject("LOWER_CONFIDENCE")
    return conflict_review(current)
```

- [ ] **Step 4: Run GREEN and full domain regression**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_identity.py tests/shared_memory/test_models.py tests/shared_memory/test_policy.py -q`

Expected: all shared-memory domain tests pass; NOOP keeps version, every accepted MERGE/REPLACE increments once.

---

### Task 3: MySQL models, migration, and repository

**Files:**
- Create: `backend/app/models/shared_memory.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/20260827_03_shared_memory_control_plane.py`
- Create: `backend/app/shared_memory/protocols.py`
- Create: `backend/app/shared_memory/sqlalchemy_repository.py`
- Test: `backend/tests/shared_memory/test_sql_models.py`
- Test: `backend/tests/shared_memory/test_sqlalchemy_repository.py`
- Test: `backend/tests/concurrency/test_shared_memory_optimistic_lock.py`

**Interfaces:**
- Produces: `MemoryControlRepository.begin_or_replay(command, fingerprints)`, `load_fact(fact_key)`, `record_decision(...)`, `mark_applying(...)`, `mark_partial(...)`, `finalize_applied(...)`, `append_attempt(...)`, `get_mutation(mutation_id)`.
- Converts: SQLAlchemy `StaleDataError` -> `MemoryVersionConflict`; unique idempotency races -> replay or `MemoryIdempotencyConflict`.

- [ ] **Step 1: Write schema and repository RED tests**

```python
def test_shared_memory_fact_uses_real_optimistic_lock():
    assert SharedMemoryFact.__mapper__.version_id_col is SharedMemoryFact.__table__.c.version

def test_memory_idempotent_replay(factory):
    first = repository.begin_or_replay(command(), fingerprints())
    second = repository.begin_or_replay(command(), fingerprints())
    assert second.mutation_id == first.mutation_id
    assert second.replayed is True
```

Cover JSON fields, numeric confidence, unique fact/idempotency keys, evidence dedupe, immutable request fields, append-only attempts, current fact queries excluding logical expiry, and a two-session stale update that raises `StaleDataError` before translation.

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_sql_models.py tests/shared_memory/test_sqlalchemy_repository.py tests/concurrency/test_shared_memory_optimistic_lock.py -q`

Expected: model/repository imports fail.

- [ ] **Step 3: Implement additive SQLAlchemy models and Alembic migration**

```python
class SharedMemoryFact(TimestampMixin, Base):
    __tablename__ = "shared_memory_facts"
    fact_key: Mapped[str] = mapped_column(String(68), unique=True, nullable=False)
    value_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}
```

Create tables in dependency order: `memory_mutations`, `shared_memory_facts`, `memory_evidence`, `memory_mutation_attempts`. Use MySQL-compatible nullable-add/backfill/alter patterns if an existing table is touched; do not use a server default on TEXT.

- [ ] **Step 4: Implement repository transactions and error translation**

Ensure rejected/conflict/noop mutations commit once without data-plane changes. `finalize_applied` checks before-version in the same session, inserts/updates the fact, attaches accepted evidence, and marks the mutation APPLIED atomically.

- [ ] **Step 5: Run GREEN and migration validation**

Run focused tests, then `cd backend; ..\.venv\Scripts\alembic.exe upgrade head` against the test database configured by the test fixture.

Expected: tests pass; migration creates only additive V2-B tables and indexes.

---

### Task 4: Independent Redis memory mutation lock

**Files:**
- Create: `backend/app/shared_memory/redis_lock.py`
- Test: `backend/tests/shared_memory/test_memory_mutation_lock.py`
- Integration test: `backend/tests/integration/test_real_memory_mutation_lock.py`
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.docker.env.example`

**Interfaces:**
- Produces: `MemoryMutationLock.acquire(fact_key) -> LockHandle`, `release(handle) -> bool`.
- Uses: key `countyflow:lock:memory:<fact_key>`, `SET NX PX`, random token, compare-and-delete release.

- [ ] **Step 1: Write fake and real-client RED tests**

```python
async def test_two_real_clients_cannot_hold_same_fact_lock(redis_a, redis_b):
    first = await lock(redis_a).acquire(FACT_KEY)
    second = await lock(redis_b).acquire(FACT_KEY)
    assert (first.acquired, second.acquired) == (True, False)
```

Also test TTL recovery, wrong-token release, independent dispatch/memory namespaces, Redis error redaction, and settings validation that `lock_ttl_ms >= timeout_ms + 1000`.

- [ ] **Step 2: Confirm RED with fake Redis tests**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_memory_mutation_lock.py -q`

Expected: missing lock class/settings.

- [ ] **Step 3: Implement the smallest independent lock**

Reuse `LockHandle` semantics but do not reuse `countyflow:lock:dispatch:` keys. Do not add lock renewal or global/entity locks.

- [ ] **Step 4: Run fake GREEN and real Redis integration**

Run focused pytest, then run the integration marker against Docker Redis with two separately constructed clients.

Expected: one client acquires; the other cannot; token-safe release and TTL recovery pass.

---

### Task 5: Idempotent Qdrant and Neo4j projection adapters

**Files:**
- Create: `backend/app/shared_memory/qdrant_projection.py`
- Create: `backend/app/shared_memory/neo4j_projection.py`
- Modify: `backend/app/memory/qdrant_repository.py`
- Modify: `backend/app/graph_memory/neo4j_repository.py`
- Test: `backend/tests/shared_memory/test_qdrant_projection.py`
- Test: `backend/tests/shared_memory/test_neo4j_projection.py`
- Modify tests: `backend/tests/memory/test_entity_memory.py`
- Modify tests: `backend/tests/graph_memory/test_neo4j_repository.py`

**Interfaces:**
- Produces: `MemoryProjectionPort.stage(projection)`, `probe(mutation_id, version)`, `activate(projection)`, `retire_previous(projection)`.
- Qdrant deterministic point: UUID5 of `countyflow-shared-memory:<vector_memory_id>:v<control_version>`.
- Neo4j deterministic projection: allowlisted relation type plus parameterized `control_fact_key`, `control_version`, and `mutation_id`.

- [ ] **Step 1: Write retry and compatibility RED tests**

```python
async def test_memory_qdrant_retry_no_duplicate(qdrant_projection):
    await qdrant_projection.stage(PROJECTION_V8)
    await qdrant_projection.stage(PROJECTION_V8)
    assert await qdrant_projection.count_points(MEMORY_ID, version=8) == 1

async def test_memory_neo4j_retry_no_duplicate(graph_projection):
    await graph_projection.stage(PROJECTION_V8)
    await graph_projection.stage(PROJECTION_V8)
    assert await graph_projection.count_edges(FACT_KEY, version=8) == 1
```

Add the mandatory visibility tests `test_qdrant_staged_projection_not_recalled`, `test_neo4j_staged_relation_not_recalled`, `test_qdrant_activation_retires_previous_version`, and `test_neo4j_activation_retires_previous_version`. Assert every Cypher value is parameterized, labels/types come from V2-A enums, graph control version equals MySQL prospective version, STAGED/RETIRED/expired projections are excluded, and legacy V1/V2-A records lacking projection metadata remain readable.

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_qdrant_projection.py tests/shared_memory/test_neo4j_projection.py -q`

Expected: missing projection adapters and active compatibility filter.

- [ ] **Step 3: Implement deterministic stage/probe/activate/retire operations**

```python
point_id = str(uuid5(NAMESPACE_URL, f"countyflow-shared-memory:{memory_id}:v{control_version}"))
payload = {"memory_id": memory_id, "fact_key": fact_key, "mutation_id": mutation_id,
           "control_version": control_version, "projection_status": "STAGED", "expires_at": expires_at}
```

Neo4j uses `MERGE` on a deterministic projection identity and never accepts a command-supplied label or relation literal.

- [ ] **Step 4: Run GREEN plus V1/V2-A read regression**

Run focused projection tests together with `tests/memory/test_entity_memory.py` and `tests/graph_memory/test_neo4j_repository.py`. Include STAGED invisibility, activation, previous-version retirement, and legacy-record compatibility cases.

Expected: retry counts stay one; legacy recall behavior remains green.

---

### Task 6: SharedMemoryMutationService happy and business-terminal paths

**Files:**
- Create: `backend/app/shared_memory/service.py`
- Test: `backend/tests/shared_memory/test_mutation_service.py`
- Test: `backend/tests/shared_memory/test_idempotency.py`
- Test: `backend/tests/shared_memory/test_concurrent_mutation.py`

**Interfaces:**
- Consumes: control repository, memory lock, decision policy, vector/graph projection ports, event publisher, clock, settings.
- Produces: `mutate(command) -> MemoryMutationResult`.
- Errors: `MemoryMutationBusy`, `MemoryVersionConflict`, `MemoryIdempotencyConflict`, `MemoryMutationValidationError`.

- [ ] **Step 1: Write orchestration RED tests**

Cover all required names: `test_memory_create`, `test_memory_duplicate_noop`, `test_memory_merge_evidence`, `test_memory_replace_expired`, `test_memory_human_confirmed_replace`, `test_memory_stale_reject`, `test_memory_lower_confidence_reject`, `test_memory_conflict_requires_review`, `test_memory_low_confidence_requires_review`, `test_memory_expected_version_conflict`, `test_memory_idempotent_replay`, `test_memory_idempotency_payload_conflict`, `test_memory_fact_optimistic_lock`, `test_memory_mutation_lock`, and `test_memory_concurrent_mutation_race`.

```python
async def test_memory_idempotent_replay(service, ports):
    first = await service.mutate(COMMAND)
    second = await service.mutate(COMMAND)
    assert second == first
    assert (ports.vector.calls, ports.graph.calls, ports.events.terminal_calls) == (1, 1, 1)
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_mutation_service.py tests/shared_memory/test_idempotency.py tests/shared_memory/test_concurrent_mutation.py -q`

Expected: service missing.

- [ ] **Step 3: Implement validation, lock, idempotency, policy, fixed staging order, MySQL finalize, activation, retirement, and APPLIED proof**

```python
async def mutate(self, command):
    prepared = self._canonicalize(command)
    handle = await self._lock.acquire(prepared.fact_key)
    if not handle.acquired:
        raise MemoryMutationBusy(prepared.fact_key)
    try:
        replay = self._repository.begin_or_replay(prepared)
        if replay.is_replay:
            return replay.result
        decision = self._policy.evaluate(self._repository.load_fact(prepared.fact_key), prepared)
        return await self._apply_decision(prepared, decision)
    finally:
        await self._lock.release(handle)
```

NOOP/REJECT/CONFLICT must make zero projection calls. Low-confidence CREATE stores a PENDING_REVIEW fact but no active projection. Matching replay emits no duplicate terminal event.

- [ ] **Step 4: Run GREEN and race tests**

Run the focused suite. The controlled two-writer race must produce exactly one version advance; the other writer returns/raises a version conflict or safely re-evaluates after acquiring the lock.

---

### Task 7: Partial failure and explicit reconciliation

**Files:**
- Create: `backend/app/shared_memory/reconciler.py`
- Test: `backend/tests/shared_memory/test_partial_failure.py`
- Test: `backend/tests/shared_memory/test_reconciliation.py`

**Interfaces:**
- Produces: `MemoryMutationReconciler.resume_mutation(mutation_id: str) -> MemoryMutationResult`.
- Reuses: same fact lock, immutable command, store probes, repository transitions, and service finalizer.

- [ ] **Step 1: Write both-direction partial RED tests**

```python
async def test_memory_partial_qdrant_success(service, ports):
    ports.graph.fail_once("NEO4J_WRITE_FAILED")
    result = await service.mutate(COMMAND_BOTH)
    assert (result.status, result.vector_status, result.graph_status) == ("PARTIAL", "STAGED", "FAILED")
    assert repository.current_fact(FACT_KEY).version == 7

async def test_memory_reconciliation(reconciler, ports):
    result = await reconciler.resume_mutation(PARTIAL_MUTATION_ID)
    assert result.status == "APPLIED"
    assert ports.vector.prepare_calls == 1
    assert ports.graph.prepare_calls == 2
```

Add the reverse test for Neo4j success/Qdrant failure, `test_partial_mutation_keeps_old_projection_active`, `test_finalize_crash_is_reconciled`, `test_applied_requires_all_projections_active`, a stale-finalize conflict test, append-only attempt verification, and STAGED orphan invisibility verification.

Name the reverse test `test_memory_partial_neo4j_success` so both required partial directions remain independently selectable.

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory/test_partial_failure.py tests/shared_memory/test_reconciliation.py -q`

Expected: partial/reconciler paths missing.

- [ ] **Step 3: Implement PARTIAL transitions and resume-only-failed behavior**

Probe when ledger/store state is uncertain. Never recreate a confirmed STAGED/ACTIVE store artifact. Recheck canonical before-version before finalization; if it already equals this mutation's after-version, resume activation instead of conflicting. If it advanced to another version, mark CONFLICT and leave STAGED artifacts invisible. Mark APPLIED only after all required projections probe ACTIVE and all prior versions are RETIRED/excluded.

- [ ] **Step 4: Run GREEN and all shared-memory tests**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/shared_memory tests/concurrency/test_shared_memory_optimistic_lock.py -q`

Expected: all fake/unit state-machine and recovery tests pass.

---

### Task 8: Audit-safe events, settings, runtime, and management API

**Files:**
- Create: `backend/app/shared_memory/events.py`
- Modify: `backend/app/events/models.py`
- Create: `backend/app/api/v1/memory_schemas.py`
- Create: `backend/app/api/v1/memory_mutations.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/app/core/config.py`
- Modify: `docker-compose.yml`
- Test: `backend/tests/shared_memory/test_audit.py`
- Test: `backend/tests/shared_memory/test_secret_safety.py`
- Test: `backend/tests/api/test_memory_mutations.py`
- Modify test: `backend/tests/api/test_cors.py`
- Modify test: `backend/tests/unit/test_settings.py`
- Modify test: `backend/tests/unit/test_runtime.py`

**Interfaces:**
- Endpoints: POST `/api/v1/memory/mutations`, GET `/api/v1/memory/mutations/{mutation_id}`, GET `/api/v1/memory/facts/{fact_key}`.
- Events: REQUESTED, APPLIED, REJECTED, CONFLICT, PARTIAL on the existing broker.

- [ ] **Step 1: Write API/settings/security RED tests**

```python
def test_production_rejects_enabled_mutation_api_without_authorization():
    with pytest.raises(ValidationError, match="authorization"):
        Settings(runtime_profile="production", memory_mutation_api_enabled=True, memory_mutation_authorization_provider="disabled", **REAL_SETTINGS)

def test_memory_secret_safety(client):
    response = submit_failing_mutation(client, evidence="Bearer must-not-leak")
    assert "must-not-leak" not in response.text
    assert "must-not-leak" not in persisted_safe_audit()
```

Add `test_memory_audit` to assert requester, source, fact key, before/after versions, decision reason, vector/graph states, and final version are reconstructable from mutation/evidence/attempt rows without secrets.

Assert HTTP 409 codes distinguish version conflict, idempotency conflict, and lock busy; PARTIAL returns 202; domain CONFLICT_REVIEW returns a typed terminal response; disabled API returns 404/503 according to the selected router guard; CORS remains restricted.

- [ ] **Step 2: Confirm RED**

Run focused API/settings/audit tests and verify missing modules/events/settings fail.

- [ ] **Step 3: Implement safe schemas, router, DI, and event adapter**

Responses expose bounded fact/mutation/evidence summaries only. Do not expose `human_confirmed` as authenticated authority. Configure docker-dev for acceptance; keep default disabled and production rejected without an authorization provider.

- [ ] **Step 4: Run GREEN and API regression**

Run shared-memory API tests plus all existing `backend/tests/api` tests.

Expected: memory API is documented in OpenAPI when enabled; dispatch endpoints and task events remain unchanged.

---

### Task 9: Minimal Memory page control-plane view

**Files:**
- Create: `frontend/src/types/memory.ts`
- Create: `frontend/src/services/api/memory-client.ts`
- Modify: `frontend/src/pages/memory-page.tsx`
- Modify: `frontend/src/hooks/use-workspace-data.ts`
- Modify: `frontend/src/styles/index.css`
- Create: `frontend/tests/memory-control-plane.test.tsx`
- Modify: `frontend/tests/workspace-services.test.ts`

**Interfaces:**
- Consumes: canonical fact and mutation-history GET endpoints.
- Produces: current fact/version/confidence/status/expiry and bounded mutation decision history.

- [ ] **Step 1: Write UI RED tests**

```tsx
it("shows canonical version and mutation decisions without enabling unauthenticated approval", async () => {
  render(<MemoryPage />);
  expect(await screen.findByText("Version 8")).toBeVisible();
  expect(screen.getByText("CONFLICT_REVIEW")).toBeVisible();
  expect(screen.getByRole("button", { name: "人工确认" })).toBeDisabled();
  expect(screen.getByText(/授权尚未配置/)).toBeVisible();
});
```

- [ ] **Step 2: Confirm RED**

Run: `cd frontend; npm test -- --run memory-control-plane.test.tsx`

Expected: missing API types/detail/history UI.

- [ ] **Step 3: Implement the minimal read-only panel**

Keep existing Memory page structure and mock labels. Do not add a mutation wizard or pretend approval is authorized. Render unavailable values with an em dash.

- [ ] **Step 4: Run GREEN, lint, and build**

Run focused Vitest, `npm run lint`, and `npm run build`.

Expected: UI tests/lint/build pass without redesigning unrelated pages.

---

### Task 10: Real four-store failure, race, and reconciliation acceptance

**Files:**
- Create: `scripts/shared_memory_integration.py`
- Create: `scripts/test-shared-memory.ps1`
- Modify: `backend/tests/unit/test_docker_runtime_files.py`
- Modify: `scripts/test-docker.ps1`
- Create: `backend/tests/integration/test_real_shared_memory_race.py`

**Interfaces:**
- Uses the existing nine Docker services; adds no tenth permanent service.
- Controlled failure is injected through projection-port wrappers in the integration runner, not by corrupting credentials or stopping unrelated containers.

- [ ] **Step 1: Write executable/config RED tests**

Assert the scripts are relative, do not print secrets, require two independent Redis clients/two MySQL sessions, test both partial directions, report before/after point/edge counts, and expose `--help` without connecting.

- [ ] **Step 2: Confirm RED**

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest tests/unit/test_docker_runtime_files.py tests/integration/test_real_shared_memory_race.py -q`

Expected: integration runner and real race fixture missing.

- [ ] **Step 3: Implement real acceptance scenarios**

The runner must prove:

```text
Redis: exactly one fact lock holder
MySQL: exactly one version-7 -> version-8 winner
Qdrant success + Neo4j injected failure: PARTIAL -> APPLIED, same versioned point count = 1
Neo4j success + Qdrant injected failure: PARTIAL -> APPLIED, same versioned edge count = 1
Before reconciliation in both directions: new version remains STAGED and invisible; normal vector and graph recall return only the previous ACTIVE version
After reconciliation in both directions: new version ACTIVE, previous version RETIRED, mutation APPLIED
Finalize crash: MySQL after-version + incomplete projection activation is reported as reconciling and resumes without duplicates
Audit: one mutation row, two attempt rows for each partial/reconcile case
```

- [ ] **Step 4: Run real integration**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-shared-memory.ps1`

Expected: structured safe output reports all four scenarios passed and no credential values.

---

### Task 11: Full V1/V2-A/V2-B regression and documentation closure

**Files:**
- Update: `docs/memory_spec.md` only if implementation names differ from the approved spec
- Update: `docs/design.md`
- Verify: `docs/superpowers/specs/2026-08-27-v2-b-shared-memory-design.md`
- Verify: `docs/superpowers/plans/2026-08-27-v2-b-shared-memory.md`

**Interfaces:**
- Acceptance output only; no Runtime Override or checkpoint mutation.

- [ ] **Step 1: Run backend quality gates**

Run: `.\.venv\Scripts\python.exe -m ruff check backend`

Run: `cd backend; ..\.venv\Scripts\python.exe -m pytest -q`

Expected: all existing and V2-B tests pass; record the actual count rather than predicting one.

- [ ] **Step 2: Run frontend quality gates**

Run: `cd frontend; npm run lint`

Run: `cd frontend; npm test -- --run`

Run: `cd frontend; npm run build`

Expected: all commands exit 0; record actual test counts.

- [ ] **Step 3: Run unified and Docker gates**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-graph-memory.ps1`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-shared-memory.ps1`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-docker.ps1`

Expected: the accepted Qdrant Top-1 98% benchmark remains unchanged; Neo4j multi-hop remains verified; topology remains eight agents; core result remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`; Redis Pending is 0; worker recovery remains below five seconds; previously accepted load-test artifacts are not invalidated.

- [ ] **Step 4: Run security and Git checks**

Run the existing value-based secret scan without printing secret values.

Run: `git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --check`

Run: `git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' diff --cached --check`

Run: `git -c safe.directory='C:/Users/24090/OneDrive/Desktop/县域物流识别异常' status --short`

Expected: zero secret findings and zero whitespace errors; preserve all unrelated user-owned changes.

- [ ] **Step 5: Perform scope audit**

Search for `update_state`, checkpoint mutation APIs, thread mutation locks, target-node mutation, ChatMemory runtime behavior, LLMWiki runtime behavior, and CodeGraph runtime behavior in the V2-B diff.

Expected: none are implemented. Report them explicitly as deferred rather than complete.
