# CountyFlow V2-B Shared Memory Mutation Design

## 1. Goal and stopping point

V2-B adds a safe write control plane for long-lived shared memory. It controls create, evidence merge, replacement, rejection, conflict review, logical expiry, idempotent replay, optimistic versioning, concurrent mutation, audit, partial failure, and explicit reconciliation.

This design implements only `DispatchMemory`. `ChatMemory`, `LLMWiki`, and `CodeGraph` may exist as enum values but are rejected by the V2-B application service. V2-B does not mutate `DispatchGraphState`, LangGraph checkpoints, running threads, target nodes, or runtime state versions. Those capabilities remain outside this phase.

The V1/V2-A read topology remains separate:

- `EntityMemoryService` continues Qdrant semantic recall.
- `GraphMemoryService` continues bounded Neo4j relationship recall.
- `SharedMemoryMutationService` coordinates writes; it does not become a combined read/write God Service.

## 2. Architecture decision

The selected architecture is:

```text
SharedMemoryMutationCommand
            |
            v
SharedMemoryMutationService
            |
            v
Redis fact-level mutation lock
            |
            v
MySQL control plane
  - current canonical fact
  - evidence provenance
  - mutation ledger and attempts
       /                 \
      v                   v
Qdrant projection     Neo4j projection
       \                 /
        v               v
      mutation result + audit event
```

MySQL is the control-plane truth. Qdrant and Neo4j are independently retryable projections. Redis provides temporary mutual exclusion only. There is no distributed transaction, two-phase commit, XA, Seata, Temporal, Saga framework, Kafka, or new message broker.

### Alternatives considered

1. **Recommended: normalized fact, evidence, mutation, and attempt records.** This preserves a small current row, append-only provenance, explicit retries, and queryable audit. It costs four focused tables but makes partial recovery and race analysis observable.
2. **Evidence JSON inside `SharedMemoryFact`.** This is initially simpler but causes unbounded row growth, repeated large text, poor deduplication, and weak provenance queries. It is rejected.
3. **Mutation ledger as the only source, deriving current facts by replay.** This is clean event sourcing but makes normal reads, expiry, optimistic locking, and migrations unnecessarily complex for the current scale. It is rejected.

## 3. Domain contracts

### 3.1 Categories and fact kinds

`MemoryCategory` contains `ChatMemory`, `LLMWiki`, `CodeGraph`, and `DispatchMemory`. V2-B accepts only `DispatchMemory`.

`MemoryFactKind` contains:

- `ATTRIBUTE`: a single-valued subject slot, such as `Vehicle:vehicle-a STATUS`;
- `RELATIONSHIP`: a set-valued subject/predicate/object relationship;
- `EXPERIENCE`: a semantic historical dispatch experience projected to Qdrant;
- `HYBRID`: an experience with both vector text and structured graph meaning.

`MemoryTarget` contains `VECTOR` and `GRAPH`. `BOTH` is represented as the validated set `{VECTOR, GRAPH}`, not as a third infrastructure path. A predicate/fact-kind registry determines allowed targets. API callers and Agents cannot arbitrarily redirect a mutation to a store.

### 3.2 Stable identity and fingerprints

Python `hash()` is forbidden. All hashes use UTF-8 canonical JSON with sorted keys, compact separators, normalized enum values, stripped IDs, and `SHA-256`.

`fact_key` identifies a logical current slot:

- `ATTRIBUTE`: category + fact kind + subject type/id + predicate. The value is excluded so `Normal` and `Broken` conflict in the same slot.
- `RELATIONSHIP`: category + fact kind + subject type/id + predicate + object type/id. The object participates because each relationship is an independently valid set member.
- `EXPERIENCE` and `HYBRID`: category + fact kind + subject + predicate + stable object/context identity supplied by the domain command.

The persisted format is `smf_<64 lowercase hex characters>`. The unhashed canonical identity is reconstructable from the fact columns.

`content_fingerprint` hashes subject, predicate, object, and normalized `value_json`, but excludes confidence and evidence. It determines whether the incoming fact changes semantic content.

`payload_fingerprint` hashes every semantic command field except `idempotency_key` and server-generated request time. It includes identity, value, expected version, confidence, incoming timestamp, human-confirmed flag, operator/source fields, bounded evidence, expiry, and validated targets. This detects one idempotency key reused with a different request.

`evidence_fingerprint` hashes source type/id, evidence text or reference, observed time, and confidence. It prevents duplicate provenance rows.

### 3.3 Mutation command schema

`SharedMemoryMutationCommand` is frozen and JSON serializable. It contains:

- required `idempotency_key`, category, fact kind, subject type/id, predicate, incoming confidence/timestamp, source type/id, operator ID, human-confirmed flag, and reason;
- optional object type/id, structured `value_json`, expected version, expiry, evidence text/reference/observed time, vector memory ID, and graph fact key;
- validated target intent, which the fact registry narrows to the allowed VECTOR/GRAPH set.

The canonical UTF-8 representation of `value_json` is limited to 16 KiB. The complete `proposed_fact_json` ledger snapshot is limited to 32 KiB. IDs and idempotency keys follow their database column limits; reasons are at most 512 characters. Commands with naive timestamps, non-finite numbers, unknown predicates/types, illegal target combinations, or oversized fields are rejected before lock acquisition.

## 4. MySQL control-plane schema

All enumerated values are stored as bounded strings and validated in the domain layer. Confidence uses `Decimal` mapped to `NUMERIC(5,4)`, never binary floating point.

### 4.1 `shared_memory_facts`

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT PK | Internal row identity |
| `fact_id` | VARCHAR(36), unique, not null | External immutable UUID |
| `fact_key` | VARCHAR(68), unique, not null | Deterministic logical slot key |
| `category` | VARCHAR(32), not null | V2-B accepts `DispatchMemory` |
| `fact_kind` | VARCHAR(32), not null | ATTRIBUTE/RELATIONSHIP/EXPERIENCE/HYBRID |
| `subject_type` | VARCHAR(64), not null | Allowlisted domain type |
| `subject_id` | VARCHAR(128), not null | Stable business ID |
| `predicate` | VARCHAR(64), not null | Allowlisted predicate |
| `object_type` | VARCHAR(64), nullable | Required for relationship/hybrid identity |
| `object_id` | VARCHAR(128), nullable | Stable object ID |
| `value_json` | JSON, not null | Canonical structured value, size-limited by service |
| `content_fingerprint` | CHAR(64), not null | Semantic equality check |
| `version` | INTEGER, not null, default 1 | SQLAlchemy `version_id_col` |
| `confidence` | NUMERIC(5,4), not null | Current accepted confidence |
| `status` | VARCHAR(32), not null | ACTIVE/EXPIRED/PENDING_REVIEW/CONFLICT |
| `expires_at` | DATETIME, nullable | Logical expiry boundary |
| `vector_memory_id` | VARCHAR(128), nullable | Stable logical Qdrant memory ID |
| `graph_fact_key` | VARCHAR(255), nullable | Stable logical graph relation identity |
| `last_mutation_id` | VARCHAR(36), not null | Mutation that produced the current row |
| `created_at`, `updated_at` | DATETIME, not null | UTC audit timestamps |

Indexes cover `(category, status)`, `(subject_type, subject_id, predicate)`, and `expires_at`. `fact_key` uniqueness and `version_id_col` prevent duplicate current slots and lost updates. `REJECTED` is not a current fact status; it exists only in the mutation ledger.

Logical reads treat `expires_at <= now` as expired even if a maintenance job has not changed the stored status. Physical deletion and a TTL cleanup daemon are deferred.

### 4.2 `memory_evidence`

Evidence is a separate append-only table because provenance grows independently from the current fact.

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT PK | Internal identity |
| `evidence_id` | VARCHAR(36), unique | External immutable UUID |
| `mutation_id` | VARCHAR(36), FK, not null | Mutation that supplied evidence |
| `fact_id` | VARCHAR(36), nullable, indexed | Set after evidence becomes accepted |
| `evidence_fingerprint` | CHAR(64), not null | Deduplication identity |
| `source_type`, `source_id` | VARCHAR(64/128), not null | Provenance source |
| `evidence_text` | TEXT, nullable | Sanitized text, maximum 2,000 UTF-8 characters |
| `evidence_ref` | VARCHAR(512), nullable | Bounded external reference without credentials |
| `observed_at` | DATETIME, not null | Evidence observation time |
| `confidence` | NUMERIC(5,4), not null | Evidence confidence |
| `safe_summary` | VARCHAR(512), nullable | Redacted operator-facing summary |
| `created_at` | DATETIME, not null | Append time |

At least one of `evidence_text` or `evidence_ref` is required. `(mutation_id, evidence_fingerprint)` is unique. Evidence rejected or held for review remains linked to its mutation but not to an accepted `fact_id`.

## 5. Mutation ledger schema

### 5.1 `memory_mutations`

Each API/service command creates one durable ledger row. Request, identity, fingerprint, proposed payload, and decision fields are immutable after creation. Operational status fields may move only through the documented state machine; every attempt is separately appended.

Required fields are:

- `id`, immutable `mutation_id`, unique `idempotency_key`, and unique `payload_fingerprint` per idempotency key;
- `fact_key`, `category`, `fact_kind`, `requested_at`, `source_type`, `source_id`, and `operator_id`;
- nullable `expected_version`, `incoming_confidence`, `incoming_timestamp`, `human_confirmed`, bounded `reason`, and validated `targets_json`;
- bounded `proposed_fact_json` containing no vector, credential, authorization header, or provider request;
- `decision`: CREATE, MERGE, REPLACE, REJECT, CONFLICT_REVIEW, or NOOP;
- nullable `before_version` and `after_version`;
- `status`: PENDING, APPLYING, FINALIZING, APPLIED, PARTIAL, REJECTED, CONFLICT, or FAILED;
- `vector_status` and `graph_status`: NOT_REQUIRED, PENDING, STAGED, ACTIVE, RETIRED, or FAILED;
- nullable safe `error_code` and `error_summary`, `created_at`, `updated_at`, and `completed_at`.

Unique constraints cover `mutation_id` and `idempotency_key`; indexes cover `(fact_key, created_at)`, `status`, and `(vector_status, graph_status)` for reconciliation.

### 5.2 `memory_mutation_attempts`

Each initial apply or resume creates an append-only attempt row with `attempt_id`, `mutation_id`, increasing `attempt_no`, start/completion timestamps, vector and graph before/after states, result, and redacted error code/summary. `(mutation_id, attempt_no)` is unique. This table preserves retry history without repeatedly copying the full command.

## 6. Deterministic decision policy

The policy is a pure domain component. It receives the current fact, incoming command, current time, and configuration. It does not access Redis, SQLAlchemy, Qdrant, or Neo4j.

Configuration values are implementation controls, not fixed logistics truths:

- `MEMORY_AUTO_APPLY_MIN_CONFIDENCE=0.75` in docker-dev/test;
- `MEMORY_LOWER_CONFIDENCE_REJECT_DELTA=0.15` in docker-dev/test;
- production must supply reviewed values explicitly before enabling the mutation API.

Decision order matters:

| Order | Condition | Decision/status | External write | Fact/version effect |
| --- | --- | --- | --- | --- |
| 1 | Same idempotency key and same fingerprint | replay prior result | none | none |
| 2 | Same idempotency key and different fingerprint | idempotency conflict | none | none |
| 3 | `expected_version` mismatches current state | version conflict | none | current fact unchanged |
| 4 | Confidence below configured minimum and not human confirmed | CONFLICT_REVIEW / CONFLICT | none | create PENDING_REVIEW only when no current row; otherwise keep current ACTIVE |
| 5 | No current fact | CREATE | validated targets | create version 1 after all required projections succeed |
| 6 | Current fact is logically expired | REPLACE | validated targets | version +1 after success |
| 7 | Same content and duplicate evidence, with no metadata change | NOOP / APPLIED | none | version unchanged |
| 8 | Same content with new evidence or accepted confidence/expiry metadata | MERGE | only required projection metadata updates | version +1 |
| 9 | Conflicting content, human confirmed, correct expected version | REPLACE | validated targets | version +1 |
| 10 | Conflicting content, older incoming timestamp | REJECT / REJECTED | none | unchanged |
| 11 | Conflicting content lower than current confidence by configured delta | REJECT / REJECTED | none | unchanged |
| 12 | Remaining conflicting content without human confirmation | CONFLICT_REVIEW / CONFLICT | none | current ACTIVE fact unchanged |

Human confirmation is evaluated only after version validation. It may authorize a deterministic replacement decision, including a low-confidence candidate, but it is a domain input rather than proof of authorization. Production must not trust a browser boolean as an authenticated approval.

Adding accepted, non-duplicate provenance is a canonical metadata change, so MERGE increments version. NOOP never increments version.

### Required conflict example

Current `Vehicle:vehicle-a STATUS` is `Normal`, version 7, confidence 0.90.

- Incoming `Broken`, expected version 7, `human_confirmed=true` produces REPLACE and prospective version 8. After both required projections succeed, current value becomes `Broken` version 8.
- The same input with `human_confirmed=false` produces CONFLICT_REVIEW. The existing `Normal` version 7 row remains ACTIVE; the proposed `Broken` payload and evidence remain auditable in the mutation ledger.
- Expected version 6 produces `MemoryVersionConflict` before any data-plane write, regardless of human confirmation.

## 7. Version and concurrency strategy

Redis lock and MySQL optimistic locking are both required:

1. The fact-level Redis key is `countyflow:lock:memory:<fact_key>`.
2. Acquisition uses `SET NX PX` with a random token.
3. Release compares the token before deletion; a stale owner cannot release another writer's lock.
4. `MEMORY_MUTATION_TIMEOUT_SECONDS=5.0` and `MEMORY_MUTATION_LOCK_TTL_MS=10000` in docker-dev/test. Settings validation requires TTL to exceed the operation timeout by at least 1,000 ms. V2-B does not renew locks.
5. `SharedMemoryFact.version` is SQLAlchemy `version_id_col`. `StaleDataError` becomes `MemoryVersionConflict`; application-level equality checks never emulate optimistic locking.

The default granularity is one logical `fact_key`. There is no global lock. Entity-level locking is not implemented in V2-B because the selected DispatchMemory mutations change one canonical slot. A future multi-fact invariant would require a separately designed entity lock and deterministic lock ordering.

If the Redis lock expires or Redis loses mutual exclusion, MySQL unique constraints and versioning remain the final protection. The real race test uses two clients and two SQL sessions; no outcome may allow two writers to commit the same expected version.

## 8. Idempotency strategy

The service computes the canonical payload fingerprint before any write. Under the fact lock it reads `memory_mutations` by idempotency key:

- matching fingerprint returns the stored mutation result and does not call Qdrant, Neo4j, version update, evidence insertion, or event publication again;
- a different fingerprint raises `MemoryIdempotencyConflict` and preserves the original request;
- a matching PARTIAL/PENDING record is returned unchanged by ordinary command replay. Recovery is an explicit `resume_mutation(mutation_id)` operation, which reuses the original ledger row and retries only unfinished projections.

Database uniqueness on `idempotency_key` protects races outside Redis. Integrity errors are reloaded and evaluated by fingerprint.

## 9. Cross-store projection semantics

### Projection visibility protocol

Every new projection follows `STAGED -> FINALIZE -> ACTIVE`; an older visible projection follows `ACTIVE -> RETIRED`. `STAGED` is a durable preparation state, never a business-readable state. `ACTIVE` is the only V2-B state admitted by normal Entity Memory or Graph Memory recall. `RETIRED` remains available for audit/recovery but is excluded from recall.

The protocol preserves two invariants:

1. Before the MySQL canonical fact advances, the proposed version is `STAGED` in every external store and therefore invisible.
2. `MemoryMutation.status=APPLIED` is legal only when MySQL contains the prospective version, every required new projection is `ACTIVE`, and every previous projection for the logical fact is `RETIRED` or otherwise excluded from active recall.

Projection payloads/properties contain `fact_key`, `control_version`, `projection_status`, and `mutation_id`. Normal read paths use an ACTIVE-only compatibility filter: V2-B records must explicitly be `ACTIVE`, while legacy V1/V2-A records without projection metadata remain readable.

The command targets are validated by the fact registry:

- structured relationship or attribute graph fact -> GRAPH;
- historical dispatch experience -> VECTOR;
- DispatchMemory with both experience text and structured relation -> VECTOR and GRAPH.

### Qdrant

- Logical `vector_memory_id` remains stable.
- Each canonical version uses deterministic point ID `UUID5("countyflow-shared-memory:<vector_memory_id>:v<after_version>")`.
- A retry of the same mutation/version upserts the same point; it cannot increase point count.
- Payload includes `fact_key`, `mutation_id`, `control_version`, `projection_status`, and expiry. Large embeddings are never copied to MySQL.
- Existing semantic scoring and adoption policy remain unchanged. The repository adds only a compatibility-safe active/expiry filter; legacy V1 points without projection metadata are treated as ACTIVE.
- Activation changes the deterministic new point from STAGED to ACTIVE and changes every earlier ACTIVE point for the same logical memory to RETIRED. A retry upserts/updates the same point and cannot create a duplicate. Cleanup is deferred.

### Neo4j

- V2-A entity/relation allowlists, parameterized values, stable entity keys, hop limits, result limits, and timeouts remain mandatory.
- Projection identity is deterministic from `fact_key` and control version; retries use `MERGE` and cannot duplicate an edge.
- Relations store `control_fact_key`, `control_version`, `mutation_id`, confidence, expiry, source metadata, and `projection_status`.
- MySQL supplies every control version. Neo4j never increments an independent version.
- V2-A graph reads ignore STAGED, RETIRED, or expired V2-B projections while treating legacy seed relations without projection metadata as ACTIVE.
- Activation changes the deterministic new relationship version from STAGED to ACTIVE and changes every earlier ACTIVE relationship with the same control fact key to RETIRED in an idempotent parameterized transaction.

The system provides effective consistency, not a distributed transaction. MySQL remains authoritative for control-plane reads, STAGED projections are hidden, and retry/reconciliation converges the stores. V2-B does not claim serializable reads across all three systems.

## 10. Mutation lifecycle

The explicit state machine is:

```text
PENDING -> APPLYING -> FINALIZING -> APPLIED
                   \-> PARTIAL -> APPLYING -> FINALIZING -> APPLIED
                   \-> FAILED
PENDING -> REJECTED
PENDING -> CONFLICT
```

Processing order:

1. Validate and canonicalize the command; calculate fact key and fingerprints.
2. Acquire the Redis fact lock within the operation timeout.
3. Check idempotency in MySQL.
4. Load the current fact and verify `expected_version`.
5. Compute the deterministic decision and prospective version.
6. Commit the mutation ledger, evidence candidate, and first attempt record.
7. For NOOP, REJECT, or CONFLICT_REVIEW, persist the terminal business outcome without external writes and release the lock.
8. Mark APPLYING and write every required projection as STAGED in the fixed order VECTOR then GRAPH. A failure on one side does not prevent attempting the other side, because both partial directions must be observable and recoverable. Each adapter call has an explicit timeout and idempotent identity.
9. If either staging operation fails, mark its store FAILED, preserve STAGED status on the other store, mark the mutation PARTIAL, keep the previous canonical ACTIVE fact unchanged, complete the attempt, and release the lock. All new STAGED artifacts remain invisible.
10. When all required projections are STAGED, use one optimistic MySQL transaction to insert/update the canonical fact to the prospective version, attach accepted evidence, and move the mutation to FINALIZING. The mutation is not yet APPLIED.
11. Activate every new deterministic projection, then retire every previous ACTIVE version. Activation and retirement are idempotent. A failure leaves the mutation FINALIZING/PARTIAL with exact per-store status for reconciliation; normal reads still admit only ACTIVE projections.
12. Only after probes prove the MySQL canonical version, all required new ACTIVE projections, and no prior ACTIVE projection, mark the mutation APPLIED.
13. Publish one terminal mutation event and release the lock in `finally`. Failure to publish an event does not roll back a durable mutation; it is recorded as a safe audit warning.

The fixed VECTOR-before-GRAPH order is operational ordering, not a distributed transaction. Reconciliation never recreates a store already proven STAGED or ACTIVE. The only pre-finalize new artifacts are STAGED and invisible. If a process crashes after MySQL advances but before one or both projections activate, the mutation remains FINALIZING/PARTIAL; control-plane reads report `projection_incomplete=true`, while normal vector/graph reads continue to return only currently ACTIVE data until `resume_mutation()` completes activation and retirement.

## 11. Partial failure and reconciliation

`MemoryMutationReconciler.resume_mutation(mutation_id)` is an explicit application service. V2-B does not add a permanent scheduler.

For each nonterminal mutation it:

1. loads the immutable command and current store states;
2. acquires the same fact lock;
3. rechecks idempotency and whether the canonical is still at the before-version or has already reached this mutation's after-version;
4. probes each target by mutation ID and control version when the ledger state is uncertain;
5. skips deterministic artifacts already STAGED/ACTIVE and retries only missing/FAILED staging work;
6. advances MySQL exactly once after all required projections are STAGED, or recognizes that this mutation already advanced it;
7. activates new projections, retires prior ACTIVE projections, and marks APPLIED only after probes prove all visibility invariants;
8. records a new append-only attempt.

If another mutation has advanced the canonical fact, reconciliation marks the old mutation CONFLICT and leaves its inactive projection artifacts hidden. Physical artifact cleanup is deferred.

### Crash windows

| Crash window | Durable observation | Recovery |
| --- | --- | --- |
| After lock, before ledger | no mutation row | TTL releases lock; original request safely starts again |
| After ledger creation | PENDING/APPLYING row | same idempotency key returns that mutation; explicit reconciliation resumes it |
| After Qdrant STAGED write | vector probe finds same mutation/version STAGED | skip duplicate point; continue GRAPH; normal recall still returns the old ACTIVE point |
| After Neo4j STAGED write | graph probe finds same deterministic projection STAGED | skip duplicate edge; continue VECTOR/finalize; normal recall still returns the old ACTIVE relation |
| Both stores STAGED before MySQL finalize | probes find both STAGED projections | recheck expected/current version and advance canonical once |
| MySQL canonical advances before activation | canonical is after-version; mutation FINALIZING; one or both projections STAGED | resume activation/retirement idempotently; mutation read API reports projection incomplete/reconciling |
| One new projection ACTIVE and the other STAGED/FAILED | mutation is not APPLIED; old versions are retired only per completed store | probe and finish only the incomplete store, then prove all stores ACTIVE and all old versions excluded |
| All projections active before APPLIED ledger write | probes prove the exact mutation/version ACTIVE and old versions RETIRED | mark APPLIED once; replay creates no store, evidence, audit, or event duplicate |
| MySQL APPLIED succeeds before response/event | APPLIED row and canonical version exist | replay returns stored result; no store or audit duplication |
| Process dies while holding lock | token remains until TTL | next caller waits/fails busy, then safely retries after TTL |

## 12. Audit and security

The mutation, evidence, and attempt records answer who requested the change, when, which fact, previous/prospective versions, proposed content, evidence provenance, expected version, decision, reason, each projection state, retry history, and final version.

The following are forbidden in fact, mutation, evidence, attempt, event, response, and log payloads: API keys, passwords, Redis credentials, database credentials, complete Authorization headers, driver/session objects, raw embedding arrays, and provider request dumps.

`evidence_text` is sanitized and capped at 2,000 characters; summaries and reasons are capped at 512 characters; references are capped at 512 characters and must not contain user-info credentials. Technical exceptions are normalized to bounded error codes and safe summaries. Secret-bearing provider exceptions are never persisted.

## 13. API boundary

V2-B includes a minimal internal/management API:

- `POST /api/v1/memory/mutations` validates and executes one mutation;
- `GET /api/v1/memory/mutations/{mutation_id}` returns ledger/result/store status without secrets;
- `GET /api/v1/memory/facts/{fact_key}` returns the canonical fact and bounded mutation/evidence history.

Terminal APPLIED/NOOP/REJECTED/CONFLICT outcomes return a typed response. Idempotency payload conflicts and expected-version conflicts return HTTP 409 with distinct safe codes. Lock contention returns HTTP 409 `MEMORY_MUTATION_BUSY`. A PARTIAL technical result returns HTTP 202 with its mutation ID so an operator can call the service-level reconciliation path.

`MEMORY_MUTATION_API_ENABLED=false` by default. Docker-dev/test may enable it for acceptance. Production configuration rejects enabling it until a real authorization dependency is provided. `human_confirmed=true`, `operator_id`, and `reason` remain auditable domain inputs, not authenticated authority.

## 14. Events and state boundary

The existing Redis event infrastructure is reused; no second broker is introduced. The mutation adapter publishes:

- `MEMORY_MUTATION_REQUESTED`;
- `MEMORY_MUTATION_APPLIED`;
- `MEMORY_MUTATION_REJECTED`;
- `MEMORY_MUTATION_CONFLICT`;
- `MEMORY_MUTATION_PARTIAL`.

Events use `mutation_id` as the correlation key and contain only mutation ID, fact key, decision, safe status, versions, and store states. Durable MySQL audit is authoritative; events are delivery/observability signals and may be replayed but do not reconstruct control truth.

No mutation command, lock, repository, ledger row, or reconciler is added to `DispatchGraphState`. The eight-agent topology remains unchanged.

## 15. Frontend boundary

V2-B does not redesign the UI. The Memory page may add a small API-backed detail block containing Current Fact, Version, Confidence, Status, Expiry, bounded evidence, and Mutation History with CREATE/MERGE/REPLACE/REJECT/CONFLICT/NOOP decisions.

The human-confirmation action remains disabled and visibly labeled as unavailable until production authorization exists. Demo/mock content remains explicitly labeled. No UI control may imply that a boolean submitted by an unauthenticated browser is a production approval.

## 16. Required verification

Unit and fake tests cover every decision branch, canonicalization, version increment, duplicate evidence, idempotency fingerprints, expiry, audit redaction, partial state, and reconciliation.

Integration evidence must include:

- two independent real Redis clients competing for one memory lock;
- two real MySQL sessions racing on one `expected_version`, with exactly one committed version advance;
- real Qdrant success plus controlled Neo4j failure, followed by reconciliation to APPLIED without a duplicate point;
- real Neo4j success plus controlled Qdrant failure, followed by reconciliation to APPLIED without a duplicate edge;
- V1/V2-A Docker regression preserving the accepted Qdrant Top-1 98% benchmark, Neo4j bounded recall, eight-agent topology, `memory-rain-li`, `national-102`, `REROUTE`, `APPROVED`, Pending 0, worker recovery under five seconds, and previously accepted load-test behavior.

## 17. Explicitly deferred Runtime Override and later capabilities

V2-B does not implement ChatMemory, LLMWiki, CodeGraph behavior, distributed transactions, automatic reconciliation scheduling, physical expiry cleanup, lock renewal, multi-fact/entity transactions, full authorization/RBAC, runtime override, `update_state(thread_id)`, checkpoint mutation, thread mutation locks, target-node mutation, or changes to a running dispatch graph.
