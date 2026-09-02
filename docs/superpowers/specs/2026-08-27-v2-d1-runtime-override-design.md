# CountyFlow V2-D1 Runtime State Override Core Design

## 1. Goal, scope, and stopping point

V2-D1 adds an authorized, idempotent, audited runtime-state override at a stable LangGraph checkpoint boundary. The only writable domain target in D1 is the canonical `Vehicle.status` value used by Capacity. A successful override from `NORMAL` to `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE` creates a new official LangGraph checkpoint, promotes it with MySQL compare-and-swap, and guarantees that the next not-yet-started Capacity node reads the new value.

This document and its implementation plan are the complete output of this design round. No production implementation is authorized by this document.

The accepted V1/V2-A/V2-B/V2-C baseline remains frozen:

- Docker remains nine services: frontend, backend, two workers, migration, Redis 8.2.9, MySQL, Qdrant, and Neo4j;
- the graph remains `Intake -> Entity Memory -> Graph Memory -> Environment -> Capacity -> Routing -> Dispatch -> Audit`;
- MySQL remains business truth and the runtime canonical-pointer control plane;
- Redis remains Streams, locks, events, and official LangGraph checkpoint storage;
- Qdrant and Neo4j remain semantic and relationship long-term memory respectively;
- `DispatchGraphState` remains typed and JSON serializable, with no client, session, repository, driver, lock, or service object in state;
- recovery remains at or below five seconds;
- the business result remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`, with one dispatch, one audit, and Pending `0`;
- the starting regression baseline is backend 413 passed/3 skipped and frontend 40 passed.

## 2. Verified implementation and official API behavior

Repository inspection on 2026-08-27 found:

- installed LangGraph is 1.2.11;
- `CompiledStateGraph.aupdate_state` has the installed signature `aupdate_state(config, values, as_node=None, task_id=None) -> RunnableConfig`;
- the current runner streams through all remaining nodes in one call, promoting MySQL after each node but not yielding ownership before the next node starts;
- `RuntimeThreadStatus` currently has `RUNNING`, `STABLE`, and `TERMINAL`;
- `RuntimeThread.state_version` and `current_checkpoint_id` already form the canonical CAS pair;
- Capacity currently reads `driver_id`, `vehicle_id`, `route_id`, and `order_id`, but no canonical runtime vehicle-status field exists;
- the runtime read authorizer is fail-closed in production when no external provider is injected;
- the existing Redis execution lock is keyed by dispatch idempotency key and does not serialize a worker with an override API request.

An executable local probe against LangGraph 1.2.11 established this exact behavior:

1. a graph paused after node `a` with next node `b`;
2. `await graph.aupdate_state(source_config, {"value": "BROKEN"}, as_node="a")` returned a new checkpoint config;
3. the new checkpoint's parent was the exact source checkpoint;
4. the updated value was visible;
5. the next node remained `b`.

Therefore D1 uses `aupdate_state` with `as_node=current_node`. It never uses `Command` for override, never treats `expected_next_node` as a goto, and never edits Redis checkpoint JSON or Redis saver keys directly.

## 3. Architecture alternatives

| Option | Result | Decision |
| --- | --- | --- |
| API-only Redis lock | The API is serialized with another API call, but a worker can still start Capacity while the API reads the Environment checkpoint | Rejected because it permits an `APPLIED` response after Capacity already read `NORMAL` |
| Route override commands through the worker stream | Serializes execution but couples management latency and authorization to dispatch message ownership; a dead worker can prevent an otherwise safe stable-state mutation | Rejected for D1 |
| MySQL single-winner boundary CAS | Worker claims `STABLE -> RUNNING`; Override takes the Redis thread lock and claims `STABLE -> OVERRIDING`; both compare the exact version/checkpoint/next-node tuple | Selected |

The selected design is the smallest approach that provides a proof of the required success semantics. It changes orchestration mechanics but does not change graph topology, Capacity thresholds, Routing scoring, Dispatch behavior, or Audit decisions.

## 4. Selected component boundaries

```text
POST override
  -> RuntimeAuthorizationProvider
  -> RuntimeOverrideService
       -> RuntimeOverrideRepository (MySQL command, attempt, CAS, audit)
       -> RuntimeBoundaryLease (Redis SET NX PX + token-safe release)
       -> RuntimeOverridePolicy (pure allowlist and transition rules)
       -> LangGraphStateUpdater (official aupdate_state/aget_state)
       -> RuntimeCheckpointStore (exact checkpoint verification)
       -> RuntimeOverrideEventPublisher (safe summaries)

Worker
  -> BoundaryExecutionCoordinator
       -> same RuntimeBoundaryLease
       -> RuntimeThreadRepository.claim_next_node(...)
       -> CheckpointedGraphRunner.run_one_boundary(...)
```

Agents do not call Redis, SQLAlchemy, the saver, or the compiled graph state-update API. The API route performs schema conversion and error mapping only. The service owns the use case. Repositories own SQL. The state updater owns LangGraph calls. The boundary lease owns Redis lock details.

## 5. Safe boundary definition

A D1 intervention boundary is safe only when every condition below is true after the caller has acquired `countyflow:lock:thread:{thread_id}` and reloaded MySQL:

1. `RuntimeThread.status == STABLE`;
2. `current_checkpoint_id` is non-null and resolves through an exact checkpoint read;
3. `state_version == command.expected_version`;
4. `terminal_at is null` and `next_node is not null`;
5. the field policy accepts `(current_node, next_node)`; for D1 this is exactly `environment -> capacity`;
6. no worker has changed the row to `RUNNING`;
7. any supplied `expected_next_node` equals the canonical `next_node`;
8. the checkpoint namespace is empty, the checkpoint belongs to the same thread, and the state passes the existing JSON and size limits;
9. the state entity ID and old value match the command.

`STABLE` means the previous node's Redis checkpoint has completed and MySQL has promoted it, while the next node has not been claimed. It is not inferred from elapsed time, Redis “latest,” a worker heartbeat, or a client-supplied checkpoint ID.

The write API performs one immediate lock attempt. It does not poll until a convenient boundary appears. Lock contention returns `RUNTIME_OVERRIDE_BUSY`; a `RUNNING` row returns `THREAD_NOT_STABLE`.

## 6. Runtime status model

D1 retains three thread statuses:

- `RUNNING`: one worker has atomically claimed the next node, or an initial/recovered execution is in progress;
- `STABLE`: a canonical checkpoint exists and no next node has been claimed;
- `TERMINAL`: execution is closed and all overrides are rejected.

`OVERRIDING` is an explicit, durable boundary-ownership state. It is acquired only by the exact MySQL CAS over `STABLE`, `state_version`, `current_checkpoint_id`, and `next_node`. A pre-checkpoint failure releases the same tuple back to `STABLE`; once an exact result checkpoint is recorded, `OVERRIDING` remains fenced until canonical promotion or exact-ID reconciliation. This supersedes the earlier transient-intent proposal and implements the approved single-winner invariant.

`state_version` changes only when the canonical state pointer changes. A `STABLE -> RUNNING` claim changes SQLAlchemy `row_version`, not `state_version`. An override promotion increments `state_version` once. `checkpoint_count` continues to count completed agent nodes and is deliberately unchanged by an override checkpoint; otherwise the next Capacity node's `completed_node_count` invariant would be off by one.

## 7. Worker/override race solution

### 7.1 One-node execution cycle

When runtime override is enabled, the graph is compiled with native `interrupt_after` boundaries for every nonterminal node. The runner executes exactly one node per call. The worker repeats this cycle:

1. acquire the per-thread boundary lease;
2. reload the exact MySQL thread row;
3. check for an unexpired matching `PENDING` override or any matching `APPLYING`/`PARTIAL` override;
4. atomically claim `(status=STABLE, checkpoint_id, state_version, next_node)` as `RUNNING`;
5. release the boundary lease;
6. invoke only the claimed node from the exact canonical checkpoint;
7. let the official saver persist the node checkpoint;
8. promote the checkpoint with the existing Redis-first/MySQL-second CAS and return the row to `STABLE`;
9. repeat until terminal.

The lease is not held while a Python node, HTTP provider, Capacity, Routing, Dispatch, or Audit runs. MySQL `RUNNING` is the durable exclusion signal during that time. Worker recovery under the existing execution lock may reclaim a stale `RUNNING` boundary from the exact canonical checkpoint; override never performs that recovery.

New thread rows become `STABLE` with `next_node=intake`, so the first node is claimed through the same protocol. D1 policy still rejects intervention before Intake because only `environment -> capacity` is allowlisted.

### 7.2 Override intent and ownership

After authorization and idempotency reservation, the command exists as a short-lived `PENDING` intent. A worker that sees a matching unexpired intent at the same version and boundary yields instead of claiming Capacity. This creates a fair intervention opportunity without a long Redis lock or a general pause feature.

The `PENDING` intent expiry is `requested_at + runtime_override_lock_ttl_ms`. A crash before lock acquisition cannot pause a worker indefinitely. Busy/rejected/conflict outcomes close the intent. Once an attempt reaches `APPLYING`, expiry no longer unblocks Worker: `APPLYING` and `PARTIAL` remain blocking until reconciliation resolves them. This protects correctness even if a process stalls beyond the Redis lease TTL.

### 7.3 Complete race outcomes

- If Override reserves intent and acquires the lease first, Worker cannot claim Capacity. Override reloads `STABLE`, promotes the new checkpoint, releases the lease, and Worker later claims Capacity from the new canonical pointer/version.
- If Worker acquires the lease and commits `STABLE -> RUNNING` first, Override may later acquire the lease but observes `RUNNING` and returns `THREAD_NOT_STABLE`.
- If both loaded version 7 earlier, the after-lock reload and MySQL CAS decide ownership. Neither an earlier API read nor Redis lock acquisition alone is sufficient.

There is no outcome in which the API returns `APPLIED` while Capacity reads the pre-override value.

## 8. Canonical vehicle state and Capacity boundary

D1 adds one actual runtime field:

```python
VehicleRuntimeStatus = Literal["NORMAL", "BROKEN", "UNAVAILABLE", "MAINTENANCE"]

class DispatchGraphState(TypedDict):
    # existing fields...
    vehicle_status: VehicleRuntimeStatus
```

This is the canonical runtime value, not `vehicle_status_override` and not a sidecar patch. It is seeded server-side before the first graph invocation by a narrow `RuntimeStateInitializer`, which resolves the assigned vehicle's current operational status through an injected application port. The external dispatch request cannot choose this value. The Docker fixture resolves `vehicle-001` to `NORMAL`; a production adapter must resolve it from the production vehicle-status source before production enablement.

Capacity receives the value explicitly:

```python
await capacity_service.evaluate(
    driver_id,
    vehicle_id,
    route_id,
    order_id,
    vehicle_status=state["vehicle_status"],
)
```

For `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE`, Capacity returns `vehicle_available=False` and `capacity_status="UNAVAILABLE"`. Its existing load thresholds and provider error behavior remain unchanged. Routing reads only Capacity output and receives no override flag, ID, or special-case branch.

## 9. Override policy matrix

Only one policy row is implemented in D1:

| Entity | Field | Entity match | Allowed from | Allowed to | Required boundary | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| `Vehicle` | `status` | `entity_id == state.vehicle_id` | `NORMAL` | `BROKEN`, `UNAVAILABLE`, `MAINTENANCE` | `current_node=environment`, `next_node=capacity` | `ALLOWED` |

All other entity types, fields, paths, values, transitions, and boundaries are rejected. In particular, D1 does not implement `BROKEN -> NORMAL`, Driver availability, Route status, Station status, arbitrary JSON Pointer, nested path input, or whole-state replacement.

`RuntimeOverridePolicy.evaluate(command, thread, state)` returns one of `ALLOWED`, `REJECTED`, or `NEEDS_DIFFERENT_BOUNDARY` plus a safe error code. The API contains no policy `if/else` chain.

Prohibited state includes `memory_top1`, `memory_results`, `graph_memory_paths`, routing decisions, dispatch results, audit results, task/thread identity, checkpoint metadata, event sequence, idempotency data, credentials, and infrastructure objects.

## 10. RuntimeOverride command and result

The client request contains:

```text
idempotency_key, entity_type, entity_id, field,
old_value, new_value, reason, expected_version, expected_next_node?
```

The server constructs the immutable domain command:

```text
override_id, idempotency_key, thread_id,
entity_type, entity_id, field, old_value, new_value, reason,
expected_version, expected_next_node,
operator_id, operator_role, operator_permissions,
requested_at
```

`override_id` is a server-generated UUID and is never accepted as a client database key. `operator_id`, role, and permissions come only from the authorization context, never from the JSON body or `human_confirmed`.

The safe result contains `override_id`, `thread_id`, `status`, `decision`, before/after version, source/result checkpoint ID, entity summary, field, old/new value, and safe error code/summary. It never returns full graph state.

## 11. MySQL override schema

Migration `20260827_05_runtime_overrides.py` adds the following tables without altering business, memory, dispatch, or audit rows.

### 11.1 `runtime_overrides`

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT primary key | internal identity |
| `override_id` | CHAR(36), unique, not null | server-generated public identity |
| `thread_id` | VARCHAR(96), FK, not null | target runtime thread |
| `task_id` | VARCHAR(36), not null | safe event correlation |
| `operator_id` | VARCHAR(128), not null | authenticated actor |
| `operator_role` | VARCHAR(64), not null | authenticated role summary |
| `idempotency_key` | VARCHAR(128), not null | client retry key |
| `payload_fingerprint` | CHAR(64), not null | canonical JSON SHA-256 |
| `expected_version` | BIGINT, not null | requested runtime version |
| `expected_next_node` | VARCHAR(32), nullable | optional precondition only |
| `before_state_version` | BIGINT, nullable | observed source version |
| `after_state_version` | BIGINT, nullable | promoted version |
| `entity_type`, `entity_id`, `field_name` | bounded VARCHAR, not null | allowlisted target |
| `old_value_json`, `new_value_json` | JSON, not null | typed scalar values |
| `reason` | VARCHAR(512), not null | sanitized operator reason |
| `decision` | VARCHAR(32), nullable | `ALLOWED`, `REJECTED`, `NEEDS_DIFFERENT_BOUNDARY` |
| `status` | VARCHAR(16), not null | lifecycle status |
| `source_checkpoint_id` | VARCHAR(64), nullable | exact canonical source |
| `result_checkpoint_id` | VARCHAR(64), nullable | exact official update result |
| `intent_expires_at` | timezone-aware DATETIME, not null | bounded worker-gate lifetime |
| `error_code` | VARCHAR(64), nullable | normalized public code |
| `error_summary` | VARCHAR(512), nullable | credential-safe summary |
| `requested_at`, `started_at`, `completed_at` | timezone-aware DATETIME | lifecycle times |
| `created_at`, `updated_at` | timezone-aware DATETIME | persistence times |

Constraints and indexes:

- unique `idempotency_key` across runtime overrides;
- index `(thread_id, status, intent_expires_at)` for the worker gate;
- index `(thread_id, requested_at)` for history;
- index `result_checkpoint_id` for explicit orphan lookup;
- values, entity, field, expected version, fingerprint, and actor are immutable after reservation; only lifecycle/result columns may transition.

### 11.2 `runtime_override_attempts`

Each apply, replay, and reconcile attempt appends a row:

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT primary key | ordering identity |
| `attempt_id` | CHAR(36), unique, not null | attempt identity |
| `override_id` | CHAR(36), FK, not null | owning command |
| `attempt_no` | INTEGER, not null | monotonic per override |
| `operation` | VARCHAR(16), not null | `APPLY`, `REPLAY`, or `RECONCILE` |
| `status` | VARCHAR(16), not null | attempt outcome |
| `observed_state_version` | BIGINT, nullable | row observed under lock |
| `source_checkpoint_id`, `result_checkpoint_id` | VARCHAR(64), nullable | exact checkpoint evidence |
| `error_code`, `error_summary` | bounded VARCHAR, nullable | safe failure |
| `authorization_ms`, `lock_ms`, `checkpoint_read_ms`, `state_update_ms`, `promotion_ms`, `total_ms` | DECIMAL(12,3), nullable | measured stages |
| `started_at`, `completed_at` | timezone-aware DATETIME | immutable timing |

Unique `(override_id, attempt_no)` prevents duplicate attempt numbering. Attempts are append-only. A second override creates a new command and cannot overwrite the first command or its attempts.

## 12. Authorization

The existing management authorization boundary is extended, not replaced:

```python
@dataclass(frozen=True)
class RuntimeAuthorizationContext:
    operator_id: str
    role: str
    permissions: frozenset[str]

class RuntimeThreadAuthorizer(Protocol):
    def authorize_read(...) -> RuntimeAuthorizationContext: ...
    def authorize_override(...) -> RuntimeAuthorizationContext: ...
```

Reads require `runtime:read` or the deployment's equivalent existing management permission. Writes require `runtime:override`. Production startup fails closed if the runtime write API is enabled without an injected external provider. Trusted authorization remains test/development-only. `human_confirmed`, headers copied into request JSON, and client-supplied `operator_id` are not authorization.

## 13. Idempotency

The fingerprint is SHA-256 over canonical UTF-8 JSON with sorted keys and compact separators. It covers `thread_id`, target entity/field, old/new values, reason, `expected_version`, and normalized `expected_next_node`. The authenticated operator is stored separately and must match on replay.

- same operator + same key + same fingerprint returns the stored result and appends at most a `REPLAY` attempt; it does not call `aupdate_state`, create a checkpoint, increment state version, or republish logical events;
- same operator + same key + different fingerprint raises `RuntimeOverrideIdempotencyConflict` with HTTP 409;
- a globally unique key already owned by another operator conflicts safely even when the payload matches and does not reveal the existing command;
- first reservation creates `PENDING` before boundary ownership so the worker can yield to the intent;
- final results are stable on replay, including `REJECTED`, `CONFLICT`, `PARTIAL`, `FAILED`, and `APPLIED`.

## 14. Official state update and checkpoint validation

`LangGraphStateUpdater` receives the compiled graph through dependency injection. For an accepted command it performs:

```python
result_config = await graph.aupdate_state(
    source_record.config,
    {"vehicle_status": command.new_value},
    as_node=thread.current_node,
    task_id=command.override_id,
)
snapshot = await graph.aget_state(result_config)
```

The service then exact-reads `result_config.configurable.checkpoint_id` through `RuntimeCheckpointStore`. It rejects promotion unless:

- result thread ID equals the command thread;
- namespace equals the configured empty namespace;
- result checkpoint ID differs from source;
- `parent_checkpoint_id == source_checkpoint_id` exactly;
- `snapshot.next == (thread.next_node,)` and no extra task is scheduled;
- `last_completed_node` and `completed_node_count` are unchanged;
- the only state difference is the allowlisted `vehicle_status` transition;
- the state is JSON serializable and below the configured checkpoint byte limit.

`as_node` preserves scheduling context; it is not accepted from the client. `task_id` is operation correlation for the official API and is not used as a checkpoint selector.

## 15. Durable override lifecycle and canonical promotion

The full lifecycle is:

1. authorize and derive the actor context;
2. compute the fingerprint and reserve/find the idempotent override row;
3. publish the logical requested event idempotently;
4. acquire `countyflow:lock:thread:{thread_id}` once;
5. reload the runtime thread under ownership;
6. reject terminal or non-stable state;
7. verify expected version and optional next-node precondition;
8. exact-read and validate the canonical checkpoint;
9. evaluate policy, entity identity, and old-value precondition;
10. transition the ledger to `APPLYING` and append an attempt;
11. call official `aupdate_state` and exact-read the returned checkpoint;
12. durably attach the explicit result checkpoint ID to the override;
13. validate direct ancestry, namespace, JSON, size, node/count, next-node, and field diff;
14. in one MySQL transaction, CAS source pointer/version/status, set pointer to result, increment `state_version` once, keep `checkpoint_count` unchanged, append `RUNTIME_OVERRIDE_APPLIED`, and finalize the override/attempt as `APPLIED`;
15. publish safe TaskEvent summaries idempotently;
16. release the token-owned lease;
17. allow the worker to claim the unchanged next node from the new canonical checkpoint.

The ordering remains Redis first, MySQL second. MySQL is never advanced before the official saver has returned and the result checkpoint has been validated.

## 16. Thread lock

The exact key is `countyflow:lock:thread:{thread_id}`. It is distinct from dispatch idempotency locks and `countyflow:lock:memory:*`.

Acquisition uses `SET key random_token NX PX ttl_ms`. Release uses an atomic compare-token-and-delete Lua script; plain `DEL` is forbidden. Values and logs contain no credentials. The API makes no retry loop. Worker contention retries are short, jittered coordination steps and never hold the lock while running a node.

The initial configuration is `runtime_override_lock_ttl_ms=10000`. The implementation records 20 real override runs, computes p99 from the ordered sample using nearest-rank, and verifies:

```text
configured TTL > max(observed override p99, observed boundary-claim p99) + 2000 ms
```

If this inequality fails, the configuration must be increased and the real suite rerun. D1 does not add lease renewal.

## 17. Failure and crash windows

| Crash/failure point | Durable truth | Required recovery |
| --- | --- | --- |
| before override reservation | no command and no state change | client may submit normally |
| after `PENDING`, before lock | canonical unchanged; expiring intent exists | reconciler closes expired intent as `FAILED`; worker proceeds after expiry |
| after lock, before `APPLYING` | canonical unchanged | lock expires; replay evaluates the stored command |
| after `APPLYING`, before Redis update | canonical unchanged; blocking command exists | reconciler retries the same override under the lease |
| Redis update fails | canonical unchanged | finalize `FAILED` with `CHECKPOINT_STORE_UNAVAILABLE`; worker may proceed |
| Redis update succeeds, process dies before result ID is recorded | unidentified noncanonical update checkpoint | never guess or promote it; mark stale `APPLYING` as `FAILED`; retention removes it |
| result ID recorded, before MySQL promotion | explicit noncanonical orphan; canonical remains old | mark/retain `PARTIAL`; stop worker resume; explicit reconciliation only |
| CAS fails because canonical version advanced | old canonical is no longer current | finalize `CONFLICT`; preserve orphan for retention; never overwrite newer state |
| MySQL promotion commits before response/event transport | new checkpoint is canonical and override is `APPLIED` | replay returns stored result; idempotent event publication completes |
| event publish fails | state and audit remain applied | event publisher/reconciler republishes by deterministic logical event key |
| worker crashes at stable boundary | canonical remains stable | override may apply; Worker 2 later resumes exact new canonical checkpoint within existing recovery SLA |

Normal `ThreadStateService` reads only MySQL `current_checkpoint_id`; no override orphan is visible. A `PARTIAL` or `APPLYING` override with explicit result blocks worker claim, so old state cannot resume while outcome is uncertain.

## 18. Override reconciliation

`RuntimeOverrideReconciler.reconcile(override_id)` loads exactly one override and its stored `source_checkpoint_id` and `result_checkpoint_id`. It never scans for “latest” and never delegates an update-origin checkpoint to the generic node-checkpoint reconciler.

Reconciliation requires:

- status `APPLYING` or `PARTIAL`;
- an explicit result checkpoint ID;
- exact source and result checkpoint records;
- result parent exactly equal to source;
- unchanged node/count/next-node invariants and exactly one allowed field diff;
- current MySQL pointer/version still equal to the command source/expected version.

If valid, it performs the same override-specific CAS and finalizes version 8. If current canonical state advanced, it finalizes `CONFLICT` and leaves the orphan until checkpoint retention. If result ID is absent, it never guesses; the override becomes `FAILED` after the intent timeout and the unidentified checkpoint remains noncanonical.

## 19. Audit and events

The command row, immutable attempts, and `runtime_thread_events` together answer who, when, thread, source checkpoint, expected/observed version, entity/field, old/new value, reason, result checkpoint, final state version, decision, and final status.

New runtime thread event types are:

- `RUNTIME_OVERRIDE_REQUESTED`
- `RUNTIME_OVERRIDE_APPLIED`
- `RUNTIME_OVERRIDE_REJECTED`
- `RUNTIME_OVERRIDE_CONFLICT`
- `RUNTIME_OVERRIDE_PARTIAL`

The same logical types are added to `TaskEventType`. Payloads contain only override ID, thread/task ID, status/decision, version numbers, safe entity/field/value summary, checkpoint IDs, and normalized error code. They contain no full state, request headers, authorization tokens, provider errors, Redis URLs, or database URLs.

Task-event publication gains an idempotent `publish_once(event_key, event)` operation. The Redis implementation atomically checks a marker, allocates the sequence, appends the stream entry, and stores the resulting event ID in one Lua script. Replays return the existing logical publication. The MySQL override/runtime event remains durable truth if event transport is temporarily unavailable.

`MEMORY_UPDATE_SUGGESTED` may be emitted as a safe advisory after `APPLIED`, but no D1 component mutates SharedMemoryFact, Qdrant, or Neo4j.

## 20. API contract

### 20.1 Routes

- `POST /api/v1/runtime/threads/{thread_id}/overrides`
- `GET /api/v1/runtime/overrides/{override_id}`
- `GET /api/v1/runtime/threads/{thread_id}/overrides?limit=20` is included as a bounded history endpoint because the ledger already supports it; it remains read-only.

First successful creation returns 201. An idempotent replay returns 200. An applied response contains:

```json
{
  "override_id": "server-uuid",
  "thread_id": "cf:dispatch:TASK-...",
  "status": "APPLIED",
  "decision": "ALLOWED",
  "before_version": 7,
  "after_version": 8,
  "source_checkpoint_id": "...",
  "result_checkpoint_id": "...",
  "entity": {"type": "Vehicle", "id": "vehicle-001"},
  "field": "status",
  "old_value": "NORMAL",
  "new_value": "BROKEN",
  "error_code": null,
  "error_summary": null
}
```

### 20.2 Error mapping

| HTTP | Code | Meaning |
| --- | --- | --- |
| 403 | `RUNTIME_OVERRIDE_FORBIDDEN` | no `runtime:override` permission |
| 404 | `THREAD_NOT_FOUND` | thread absent or deliberately hidden by authorization policy |
| 404 | `RUNTIME_OVERRIDE_NOT_FOUND` | override absent or not visible |
| 409 | `RUNTIME_STATE_VERSION_CONFLICT` | exact version mismatch |
| 409 | `RUNTIME_OVERRIDE_IDEMPOTENCY_CONFLICT` | existing key has a different actor or fingerprint |
| 409 | `RUNTIME_OVERRIDE_BUSY` | boundary lease not acquired immediately |
| 409 | `RUNTIME_STATE_PRECONDITION_FAILED` | canonical old value or entity ID differs |
| 409 | `THREAD_NOT_STABLE` | worker already claimed/runs the node |
| 409 | `THREAD_TERMINAL` | terminal write rejected |
| 409 | `RUNTIME_NEXT_NODE_CONFLICT` | supplied expected next node differs |
| 422 | `OVERRIDE_FIELD_NOT_ALLOWED` | target is outside D1 allowlist |
| 422 | `OVERRIDE_VALUE_INVALID` | enum or transition is invalid |
| 503 | `CHECKPOINT_STORE_UNAVAILABLE` | exact read or official update unavailable |

Error bodies use safe codes, messages, and bounded details only.

## 21. Success semantics

`APPLIED` means all of the following are durably true before the response is sent:

- the official new checkpoint exists;
- the new checkpoint is the exact direct child of the prior canonical checkpoint;
- MySQL points to it at `expected_version + 1`;
- the next node is unchanged and was not claimed before promotion;
- the canonical state contains the new value;
- the override ledger and runtime event record the result;
- any worker can only claim the next node after reloading the new pointer/version.

`APPLIED` does not promise that Capacity has already completed. It promises deterministic visibility when Capacity is next invoked. If any of these facts cannot be established, the response is not `APPLIED`.

## 22. Performance measurement

Each attempt records `authorization_ms`, `lock_ms`, `checkpoint_read_ms`, `state_update_ms`, `promotion_ms`, and `total_ms`. The real acceptance script performs at least 20 legal overrides and reports min, arithmetic mean, nearest-rank p95, and max for every stage.

Correctness, 20/20 application, 20/20 next-node visibility, and the TTL inequality are gates. Because no contractual latency redline was supplied, latency is reported rather than converted into an invented SLA. Any observed total in the tens-of-seconds range is an engineering failure requiring investigation before acceptance.

## 23. Test and acceptance design

The TDD plan maps every mandatory named test. The highest-value real scenario is:

```text
Environment canonical checkpoint, Vehicle A=NORMAL, state_version=7
  -> POST NORMAL -> BROKEN with expected_version=7
  -> official update checkpoint
  -> MySQL canonical version=8
  -> resume unchanged next_node=capacity
  -> Capacity executes exactly once and reads BROKEN
  -> vehicle_available=false
  -> Routing does not use Vehicle A
```

Additional real tests prove two independent clients at version 7 produce one `APPLIED`, one busy/conflict, and final version 8; Redis-success/MySQL-failure leaves V7 canonical and blocks resume; reconciliation promotes only the recorded direct successor; worker crash at the Environment boundary allows override then Worker 2 resumes the new checkpoint; 20/20 legal overrides reach the new value.

Fake/unit evidence covers policy, fingerprinting, state diff, official updater adapter contract, failures, auth, audit, secret safety, API mapping, and exact-once logical events. Real Docker evidence covers Redis locks, LangGraph Redis checkpoints, MySQL CAS, worker race/recovery, Capacity visibility, Routing exclusion, event transport, and the frozen business path.

## 24. Docker lifecycle and regression constraints

No tenth service is added. Backend and both workers receive the same boundary-lock TTL and runtime-override feature settings. The backend owns override application. Workers own graph execution and recovery. MySQL migration runs before either process. Redis 8 continues to host Streams, locks, events, and official checkpoint indexes.

Required closure runs include backend lint and full pytest, frontend lint/test/build, real MySQL/Redis/Qdrant/Neo4j integrations, two-worker crash recovery, Docker E2E, Pending `0`, and `git diff --check`. The V2-C read API and authorization behavior must remain unchanged except for the compatible context return type.

## 25. Explicit D2 and later deferrals

V2-D1 does not implement frontend action buttons, an approval workbench, arbitrary field editing, recovery transitions to `NORMAL`, rollback to historical checkpoints, replay of completed agents, skip, goto, terminal reopen, automatic Qdrant/Neo4j/shared-memory mutation, the final 15-round black-box demonstration, or formal override Locust testing.

The optional frontend change is limited to displaying override history/status in the existing read-only Thread panel. The implementation plan selects no frontend change for D1; the current panel remains read-only. D2 owns the first interactive “set Broken” workflow.

## 26. Design self-review

- No arbitrary JSON patch or client-selected state path exists.
- No Redis checkpoint payload or saver key is edited directly.
- No Qdrant, Neo4j, or SharedMemoryFact write is triggered.
- Terminal writes are rejected.
- `expected_version` and old-value checks are mandatory.
- `expected_next_node` is only a precondition and never a goto.
- Dispatch, shared-memory, and runtime versions remain separate.
- Worker and Override share the same boundary lease and after-lock MySQL CAS.
- `APPLIED` is impossible after Capacity has been claimed.
- Generic checkpoint reconciliation cannot promote an override checkpoint.
- All traversal and state reads are exact and bounded.
- Production authorization fails closed.
