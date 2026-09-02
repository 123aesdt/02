# CountyFlow V2-C Persistent Checkpoint and Thread State Design

## 1. Goal, scope, and stopping point

V2-C adds durable LangGraph checkpoints, stable thread identity, crash-safe resume, a lightweight MySQL thread registry, safe checkpoint events, read-only runtime inspection APIs, and a minimal read-only frontend panel.

V2-C does not add Runtime State Override, `update_state`, checkpoint mutation, human approval actions, target-node mutation, branch editing, replay from an arbitrary historical checkpoint, or runtime memory merge. Those operations remain V2-D work and require a separate authorization, concurrency, and audit design.

The accepted V1/V2-A/V2-B behavior is immutable for this phase:

- the graph remains the same eight agents in the same order;
- MySQL remains business and shared-memory control truth;
- Qdrant remains semantic long-term memory;
- Neo4j remains relationship long-term memory;
- Redis Streams, workers, WebSocket events, dispatch idempotency, audit idempotency, and V2-B projection behavior must not regress;
- the core result remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`, with one dispatch, one audit, and Redis Pending `0`;
- the accepted real-embedding Top-1 result remains 49/50 (98%);
- the accepted starting regression baseline is backend 356 passed plus the real four-store test, and frontend 36 passed.
- worker recovery remains <=5 seconds and the accepted Locust QPS/P95/error-rate hard metrics remain satisfied.

This document is design-only. Production code starts only after explicit V2-C TDD approval.

## 2. Verified current implementation and native LangGraph behavior

Repository inspection on 2026-08-27 established the following facts:

- `backend/pyproject.toml` specifies `langgraph>=1.2,<2`; the local environment contains LangGraph 1.2.11 and `langgraph-checkpoint` 4.2.0.
- `build_graph()` currently compiles without a checkpointer.
- the current topology is `Intake -> Entity Memory -> Graph Memory -> Environment -> Capacity -> Routing -> Dispatch -> Audit`.
- `DispatchWorker` invokes or streams the graph without a runnable config, so it supplies no `configurable.thread_id`.
- `DispatchGraphState` is a JSON-compatible `TypedDict`; infrastructure dependencies are closed over by the node builder through `GraphDependencies` and are not stored in state.
- the existing execution lock and MySQL idempotency ledger prevent concurrent duplicate execution and reconcile terminal dispatch/audit records, but a nonterminal worker crash currently starts the graph again.

An import-and-execution probe against the installed packages verified:

- `StateGraph.compile(checkpointer=..., interrupt_before=..., interrupt_after=...)` is available;
- asynchronous execution uses `BaseCheckpointSaver.aput`, `aput_writes`, `aget_tuple`, and `alist`;
- `interrupt_after=["a"]` persisted a snapshot whose next node was `b`;
- `ainvoke(None, same_thread_config)` resumed at `b` and did not execute `a` again;
- native dynamic `interrupt(value)` surfaced an interrupt and resumed only through `Command(resume=value)`;
- `astream` and `ainvoke` expose `durability`, and V2-C will explicitly use `durability="sync"`.

The Redis saver package is not currently installed. The official `langgraph-checkpoint-redis` 0.5.x line accepts `langgraph-checkpoint>=4.1.1,<5.0.0`, which includes the installed 4.2.0. It requires RedisJSON and RediSearch. The current `redis:7.4-alpine` service does not provide those modules, so the existing Redis service must move to the pinned `redis:8.2.9-alpine` image before the saver can be enabled.

## 3. Checkpoint backend decision

### 3.1 Selected architecture

V2-C uses the official asynchronous Redis implementation:

```text
langgraph-checkpoint-redis >=0.5.2,<0.6
              |
              v
AsyncRedisSaver + synchronous durability
              |
              v
existing CountyFlow Redis service, upgraded to pinned Redis 8
```

The full-history `AsyncRedisSaver` is selected. `AsyncShallowRedisSaver` is rejected because V2-C requires immutable checkpoint history and exact checkpoint reads.

The existing Redis service is reused. No new container, broker, workflow engine, or database is introduced. Docker remains exactly nine services. Existing CountyFlow Redis keys use the `countyflow:*` namespace; the official saver uses its own checkpoint key families. Real integration must prove queues, task events, locks, and checkpoints coexist in the same Redis instance.

### 3.2 Alternatives considered

| Option | Advantages | Costs and risks | Decision |
| --- | --- | --- | --- |
| Official `AsyncRedisSaver` on Redis 8 | Implements the native saver protocol, pending writes, history, async methods, serializer, TTL, and LangGraph resume semantics; reuses an existing runtime service | Requires upgrading Redis 7.4 to Redis 8 and running index setup; checkpoint data follows Redis durability rather than MySQL transaction semantics | Selected |
| Custom MySQL `BaseCheckpointSaver` | Keeps registry and payload in one database family; no Redis module requirement | There is no official MySQL saver in the selected stack; CountyFlow would have to implement serializer compatibility, pending writes, namespaces, history ordering, async behavior, and future LangGraph protocol changes; adds heavy write load to the business database | Rejected |
| Custom plain-Redis saver on Redis 7.4 | Avoids the Redis image change | Reimplements the same protocol and history behavior the maintained saver already provides; high correctness and migration risk | Rejected |

If the pinned official saver fails the real compatibility smoke test, implementation stops and reports a design blocker. V2-C must not silently substitute an unreviewed custom saver.

## 4. State boundaries and ownership

The four persistence roles remain separate:

| Store | V2-C responsibility | Explicitly not responsible for |
| --- | --- | --- |
| MySQL | business facts; dispatch/audit truth; V2-B canonical memory; lightweight runtime-thread registry and audit metadata | full LangGraph checkpoint payload |
| Redis | Streams, events, locks, and full LangGraph checkpoint history/pending writes | business source of truth |
| Qdrant | semantic long-term memory | runtime state or checkpoints |
| Neo4j | allowlisted relationship long-term memory | runtime state or checkpoints |

`DispatchGraphState` remains typed and JSON serializable. Neo4j drivers/sessions/repositories, Qdrant clients/repositories, Redis clients, SQLAlchemy sessions/factories, services, locks, event brokers, and saver objects are prohibited from state.

V2-C adds only these optional serializable observability fields:

```python
last_completed_node: NotRequired[str]
completed_node_count: NotRequired[int]
```

An instrumented node wrapper in the graph builder supplies them after a node returns successfully. They identify a persisted post-node boundary and support deterministic reconciliation without relying on private LangGraph channel names. They do not control routing.

`thread_id` is not duplicated inside `DispatchGraphState`. It exists only in LangGraph runnable config and the MySQL registry. This prevents divergence between `Config.thread_id` and a second state copy.

## 5. Stable thread identity

One accepted dispatch task maps to at most one runtime thread, enforced by a unique `task_id` in the registry. The server derives the ID once through a pure domain function:

```text
thread_id = "cf:dispatch:" + task_id
```

Allowed values match `^cf:dispatch:TASK-[a-f0-9]{31}$` and are never supplied by a graph node or external provider. This is not an assumption that `task_id == thread_id`; it is an explicit, versioned one-to-one derivation with a distinct namespace.

The registry row is created in the same MySQL transaction as the new `DispatchTask`. An idempotent API replay returns the existing task and existing thread. A queue publication failure may leave the task/thread in their initial state, but it cannot create a second thread. Worker retry, `XAUTOCLAIM`, process restart, and checkpoint resume always load the thread by `task_id` and reuse the stored `thread_id`.

## 6. MySQL runtime registry schema

Migration `20260827_04_runtime_threads.py` is additive and introduces two metadata-only tables.

### 6.1 `runtime_threads`

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT PK | internal row identity |
| `thread_id` | VARCHAR(96), unique, not null | stable external runtime identity |
| `task_id` | VARCHAR(36), unique, not null, FK to unique `dispatch_tasks.task_id` | strict one-task/one-thread mapping |
| `status` | VARCHAR(16), not null | `RUNNING`, `STABLE`, or `TERMINAL` |
| `current_checkpoint_id` | VARCHAR(64), nullable | canonical checkpoint pointer |
| `state_version` | BIGINT, not null, default 0 | canonical monotonic runtime version |
| `last_completed_node` | VARCHAR(32), nullable | node represented by the canonical pointer |
| `next_node` | VARCHAR(32), nullable | next scheduled node, null at terminal |
| `checkpoint_count` | BIGINT, not null, default 0 | number of canonical promoted checkpoints |
| `checkpoint_size_bytes` | BIGINT, nullable | serialized size of current payload |
| `last_worker` | VARCHAR(128), nullable | safe worker name, not credentials |
| `last_event_sequence` | BIGINT, nullable | last successfully published task-event sequence |
| `resumed_count` | INTEGER, not null, default 0 | successful resume count |
| `terminal_at` | timezone-aware DATETIME, nullable | terminal transition time |
| `row_version` | INTEGER, not null | SQLAlchemy `version_id_col` for row concurrency |
| `created_at`, `updated_at` | timezone-aware DATETIME | lifecycle timestamps |

Indexes cover `(status, updated_at)` and `current_checkpoint_id`. `terminal` is deliberately derived as `status == TERMINAL` instead of stored as a second boolean that could contradict status. The row stores no graph state JSON.

`order_id` is not duplicated in the registry; it is resolved through the unique `task_id` foreign key to `dispatch_tasks`, which already owns the order relationship. This keeps the registry lightweight and avoids two order identities drifting apart.

### 6.2 `runtime_thread_events`

This append-only metadata ledger provides audit and canonical checkpoint history without copying checkpoint payloads.

| Column | Type and constraint | Meaning |
| --- | --- | --- |
| `id` | BIGINT PK | ordering key |
| `event_id` | VARCHAR(36), unique | immutable event identity |
| `event_key` | VARCHAR(160), unique, not null | operation-specific idempotency key |
| `thread_id` | VARCHAR(96), FK, not null | owning thread |
| `event_type` | VARCHAR(32), not null | `THREAD_CREATED`, `THREAD_CHECKPOINTED`, `THREAD_RESUMED`, `THREAD_RECONCILED`, `THREAD_TERMINAL` |
| `checkpoint_id` | VARCHAR(64), nullable | checkpoint involved |
| `parent_checkpoint_id` | VARCHAR(64), nullable | predecessor used for chain validation |
| `state_version` | BIGINT, not null | version after this event |
| `node` | VARCHAR(32), nullable | last completed node |
| `next_node` | VARCHAR(32), nullable | next scheduled node |
| `checkpoint_size_bytes` | BIGINT, nullable | measured serialized payload size |
| `worker_name` | VARCHAR(128), nullable | safe execution identity |
| `error_code` | VARCHAR(64), nullable | normalized code only |
| `metadata_json` | JSON, not null | bounded safe metadata only |
| `created_at` | timezone-aware DATETIME | immutable event time |

Checkpoint events use `checkpoint:{checkpoint_id}` keys. Resume/recovery events include the Redis Stream message ID and delivery count, allowing distinct recoveries while suppressing a replay of the same recovery operation. Indexes cover `(thread_id, state_version)` and `(thread_id, created_at)`. There is no update method for this table.

## 7. Canonical current checkpoint and state version

Redis may contain native internal checkpoints and an unpromoted checkpoint after a partial failure. Therefore “latest in Redis” is not automatically the business-visible current state.

The sole canonical pointer is `runtime_threads.current_checkpoint_id`. Read services first load the registry, then request that exact Redis checkpoint by config containing `thread_id`, empty `checkpoint_ns`, and `checkpoint_id`. They never expose an unpromoted latest checkpoint.

`runtime_threads.state_version` is the sole canonical runtime version:

- a new thread starts at version `0` with no canonical checkpoint;
- every successful post-node checkpoint promotion increments it by exactly one;
- resume and read do not increment it;
- terminal marking does not create an extra version unless it promotes a new final post-node checkpoint;
- the version never decreases and historical events are append-only.

The native immutable LangGraph checkpoint ID remains the storage identity. The CountyFlow state version is the business-visible concurrency/order identity. Neither replaces the other.

The three existing version domains remain independent: `SharedMemoryFact.version` controls long-term memory mutations, `Dispatch.version` controls the dispatch business row, and `RuntimeThread.state_version` controls runtime thread state. No API or repository may compare or copy one domain's version as another domain's expected version.

## 8. Checkpoint write lifecycle

`CheckpointedGraphRunner` invokes `astream` with:

```python
config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
durability = "sync"
stream_mode = "updates"
```

For resume it additionally pins `checkpoint_id=current_checkpoint_id` and passes `None` as graph input.

The lifecycle for every successfully completed node is:

1. the node returns a JSON-serializable patch including `last_completed_node` and `completed_node_count`;
2. native LangGraph calls `AsyncRedisSaver.aput` and persists the immutable checkpoint before the next super-step because durability is synchronous;
3. the runner receives the node update and reads the exact latest `StateSnapshot` for the same thread;
4. it validates `last_completed_node`, parent relationship, expected next node, JSON serializability, and payload size limit;
5. one MySQL transaction performs a compare-and-swap on `(thread_id, current_checkpoint_id, state_version)`, advances the pointer/version, and appends `THREAD_CHECKPOINTED` metadata;
6. only after the transaction commits does it publish the safe task event and request the next graph update.

The first native `input`/pre-node checkpoints remain valid Redis implementation history but are not promoted as CountyFlow post-node versions. The read API labels them `internal` only when explicitly reading native diagnostic history; normal history returns canonical promoted post-node entries.

Because the current typed state already carries normalized anomaly, vector-memory results, graph-memory facts/paths, environment, capacity, routing, dispatch, and audit-related results, a post-node snapshot contains the information required for the next node. Raw embeddings, full Neo4j dumps, HTTP responses, and event history are not added to state.

If serialization or maximum-size validation fails, execution stops before the next node and emits a normalized failure without advancing the registry.

## 9. Partial failure and consistency protocol

There is no distributed transaction between Redis and MySQL. V2-C uses ordered writes, a canonical pointer, compare-and-swap, and reconciliation.

### 9.1 Redis checkpoint succeeds, MySQL promotion fails

The checkpoint is an orphan candidate, not canonical. The runner raises `CheckpointRegistryPromotionError`; it does not request the next graph update and the Redis Stream message remains pending. No `THREAD_CHECKPOINTED` task event is emitted.

On recovery, `ThreadCheckpointReconciler` loads the registry pointer and bounded Redis history. It may promote exactly one candidate only when all conditions hold:

- the candidate belongs to the same server-generated `thread_id` and empty namespace;
- its parent is the current canonical checkpoint, or both are initial and the candidate is the first completed node;
- `last_completed_node` is an allowed topology node;
- its `completed_node_count` is exactly the expected next count;
- its next node matches the fixed eight-agent topology;
- its state is JSON serializable and within the size limit;
- no canonical event already exists for the checkpoint.

Promotion uses the same MySQL compare-and-swap and appends `THREAD_RECONCILED`. Ambiguous, forked, oversized, or multi-step candidate chains are not guessed; execution remains pending with a safe audit error.

### 9.2 MySQL pointer succeeds, Redis checkpoint fails

This ordering is forbidden by construction. CountyFlow never advances the MySQL pointer before native Redis persistence returns successfully. Consequently the normal write path cannot create a registry pointer to a missing checkpoint.

If later retention or external data loss removes a pointed checkpoint, the read service reports `checkpoint_available=false` and `CHECKPOINT_EXPIRED_OR_MISSING`; it never substitutes an unverified Redis “latest” value.

### 9.3 Duplicate promotion or competing worker

The existing Redis execution lock remains the first contention guard. MySQL compare-and-swap and unique event constraints are the correctness layer. A duplicate promotion returns the already canonical result when checkpoint ID and version match; a stale or divergent writer raises `ThreadVersionConflict` and stops.

## 10. Crash resume semantics

Recovery preserves the existing Redis Streams model:

1. Worker 1 reads a task and uses its registry `thread_id`.
2. Node N completes, Redis persists its checkpoint, and MySQL promotes it.
3. Worker 1 is killed before N+1 completes and before terminal ACK.
4. The execution lock expires; Worker 2 claims the pending stream entry through `XAUTOCLAIM`.
5. Existing MySQL task reconciliation runs first. If dispatch/audit is already terminal, the worker takes the existing terminal replay path and does not run the graph.
6. Otherwise the checkpoint reconciler resolves any single safe orphan and loads the canonical pointer.
7. Worker 2 calls the same compiled graph with `input=None` and the same `thread_id` plus canonical `checkpoint_id`.
8. Native LangGraph resumes from N+1. Completed nodes are not invoked again.
9. Dispatch and audit retain their current database idempotency checks, so the crash windows around external business commits still produce at most one dispatch and one logical audit.
10. The worker marks the thread `TERMINAL`, marks the task terminal, publishes terminal events, then ACKs the stream entry.

The worker must never infer “resume” solely from delivery count. It resumes when the registry has a valid canonical checkpoint; otherwise it starts from the original task input.

## 11. Status model and terminal transition

V2-C supports exactly these runtime statuses:

- `RUNNING`: thread allocated but no post-node canonical checkpoint exists yet; this includes queued and first-node execution time;
- `STABLE`: at least one nonterminal canonical post-node checkpoint exists and is safe to resume; a worker may currently be executing the next node;
- `TERMINAL`: a formal task outcome is durable and no further automatic graph execution is allowed. `APPROVED` and `REVIEW_REQUIRED` point to the final audit checkpoint; a terminal `DLQ` may retain the last stable pointer while clearing the registry `next_node` and recording a normalized failure code.

`STABLE` means “there is a stable recovery boundary,” not “no worker is active.” This avoids a database write before every node start.

Terminal marking is idempotent. `SUBMISSION_FAILED` is not a runtime-thread terminal because the existing API may republish the same task before graph execution. If the graph is already at END on recovery, invoking with `None` returns the persisted final state; the worker retries only terminal registry/task/event/ACK steps.

## 12. Interrupt, pause, and future thread lock boundary

V2-C uses native static `interrupt_after` only in tests and the real crash harness to produce a deterministic checkpoint boundary. Normal production dispatch has no configured pause node.

Native dynamic `interrupt(value)` and `Command(resume=value)` are documented and covered by an API compatibility test, but no current agent calls `interrupt()` and no resume-value API is exposed.

Future V2-D pause/override support must use LangGraph native interrupt/update primitives behind a thread-scoped mutation lock and expected `state_version`. It must not implement a custom “pause” boolean inside business state.

The future lock key is reserved as `countyflow:lock:thread:{thread_id}` with a bounded TTL, random ownership token, compare-token renewal, and token-safe release. V2-C does not acquire it because V2-C has no external thread mutation. The current worker execution lock remains keyed by dispatch idempotency key and prevents concurrent execution.

The future V2-D lifecycle may extend the implemented `RUNNING`, `STABLE`, and `TERMINAL` states with `PAUSED_FOR_INTERVENTION` and `RESUMING`. `STABLE` is the only future mutation window; no intervention is permitted while a node is executing or after `TERMINAL` without a separately designed reopen operation.

## 13. Repository and service boundaries

### 13.1 `RuntimeThreadRepository`

The repository is the only MySQL access boundary for runtime thread metadata. It exposes:

```python
create_for_task(task_id: str, thread_id: str) -> RuntimeThreadSnapshot
get_by_thread_id(thread_id: str) -> RuntimeThreadSnapshot | None
get_by_task_id(task_id: str) -> RuntimeThreadSnapshot | None
mark_running(thread_id: str, worker_name: str) -> RuntimeThreadSnapshot
promote_checkpoint(command: PromoteCheckpoint) -> RuntimeThreadSnapshot
mark_resumed(command: MarkResumed) -> RuntimeThreadSnapshot
mark_terminal(command: MarkTerminal) -> RuntimeThreadSnapshot
list_events(thread_id: str, limit: int) -> list[RuntimeThreadEventSnapshot]
```

No graph node imports this repository.

### 13.2 `CheckpointStore`

Application code depends on a narrow async protocol implemented by an adapter around `AsyncRedisSaver`:

```python
get(config) -> CheckpointRecord | None
history(config, *, limit: int) -> list[CheckpointRecord]
delete_thread(thread_id: str) -> None
```

The compiled graph receives the underlying official saver because LangGraph requires `BaseCheckpointSaver`. Tests use `InMemorySaver` through the same runner contract. Redis clients and saver instances remain runtime dependencies and never enter state.

### 13.3 `ThreadStateService`

This read-only application service provides:

```python
get_current_by_thread(thread_id: str) -> RuntimeThreadDetail
get_current_by_task(task_id: str) -> RuntimeThreadDetail
get_checkpoint(thread_id: str, checkpoint_id: str) -> RuntimeCheckpointDetail
list_history(thread_id: str, *, limit: int) -> RuntimeThreadHistory
```

It treats the MySQL pointer as canonical, verifies exact Redis checkpoint identity, applies bounded pagination, and returns only validated JSON-compatible state.

### 13.4 `CheckpointedGraphRunner` and reconciler

The runner owns invocation config, synchronous durability, node-boundary promotion, safe event publication, and terminal handoff. `ThreadCheckpointReconciler` handles the single-orphan recovery case. The worker depends on the runner, not directly on a vendor saver.

## 14. Graph builder and dependency injection

`GraphDependencies` remains the node-service dependency object and remains outside state. A checkpointer is a graph-runtime concern, so it is injected separately:

```python
build_graph(
    dependencies: GraphDependencies,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
) -> CompiledStateGraph
```

`build_runtime_worker()` constructs one async saver per worker process, runs `asetup()` during startup, compiles the graph with it, and injects the registry, runner, reconciler, and event broker into `DispatchWorker`. API startup constructs a read-side saver/store and `ThreadStateService` only when the read API feature gate is enabled. All resources are closed on shutdown.

The eight-agent topology and every routing edge remain unchanged.

## 15. Read-only runtime API and production authorization

The optional router uses prefix `/api/v1/runtime/threads` and exposes only GET operations:

- `GET /api/v1/runtime/threads/by-task/{task_id}`;
- `GET /api/v1/runtime/threads/{thread_id}`;
- `GET /api/v1/runtime/threads/{thread_id}/history?limit=20`.

The current response includes `thread_id`, `task_id`, status, derived terminal flag, canonical `current_checkpoint_id`, `state_version`, `last_completed_node`, `next_node`, `checkpoint_count`, `last_event_sequence`, checkpoint availability, checkpoint size, timestamps, and the validated current state. History returns canonical post-node metadata in descending version order and a bounded state summary; it does not return Redis keys, serializer tags, pending-write internals, connection details, or secrets.

Settings:

```text
RUNTIME_THREAD_API_ENABLED=false
RUNTIME_THREAD_AUTHORIZATION_PROVIDER=disabled
RUNTIME_THREAD_HISTORY_LIMIT=20
RUNTIME_THREAD_HISTORY_MAX_LIMIT=100
```

The router is not mounted when the feature flag is false. `runtime_profile=production` rejects an enabled API when the authorization provider is `disabled`. A narrow `RuntimeThreadAuthorizer` checks caller access to the task/thread before service reads. V2-C supplies a trusted test/development adapter only; production deployment must inject a real authorizer. CORS does not count as authorization.

No POST, PUT, PATCH, DELETE, resume, pause, rollback, or override endpoint exists in V2-C.

## 16. Event and audit model

The existing task event enum gains:

- `THREAD_CHECKPOINTED` after a successful MySQL promotion;
- `THREAD_RESUMED` after Worker 2 successfully starts from the canonical checkpoint;
- `THREAD_TERMINAL` after the terminal registry transition.

Event payloads are bounded to safe metadata:

```text
thread_id
checkpoint_id
state_version
last_completed_node
next_node
checkpoint_size_bytes
resume_count
```

They never include full graph state, anomaly descriptions, raw memory evidence, embeddings, provider responses, authorization headers, URLs with credentials, or infrastructure exceptions. MySQL `runtime_thread_events` is the durable audit ledger; Redis task events remain the live WebSocket transport.

The event schema reserves `THREAD_PAUSED`, `THREAD_RESUMING`, and `THREAD_OVERRIDE_APPLIED` for V2-D audit compatibility, but V2-C code neither emits nor accepts them as commands.

## 17. Frontend read-only experience

The dispatch detail page gains a compact “Runtime Thread” panel when `VITE_RUNTIME_THREAD_STATE_ENABLED=true` and API mode is active. It shows:

- Thread ID;
- status (`RUNNING`, `STABLE`, `TERMINAL`);
- current/last completed node;
- next node;
- state version;
- current checkpoint ID in truncated display with full accessible text;
- checkpoint count;
- a bounded checkpoint timeline.

The panel has loading, unavailable, expired, unauthorized, and disabled states. It has no edit controls, pause/resume buttons, rollback controls, or state JSON editor. Existing dispatch playback continues to use task events and is not replaced by checkpoint history.

## 18. Retention and payload limits

The official saver is configured with bounded time retention:

```text
RUNTIME_CHECKPOINT_RETENTION_MINUTES=10080
RUNTIME_CHECKPOINT_REFRESH_ON_READ=false
RUNTIME_CHECKPOINT_MAX_BYTES=1048576
```

Seven days is an operational default, not a business truth. Writes refresh the lifetime of newly written checkpoint keys; reads do not extend retention indefinitely. Active CountyFlow dispatches are expected to complete far inside this window. MySQL registry and audit metadata may outlive Redis payloads and then report an expired/missing payload explicitly.

V2-C does not implement count-based physical pruning because the selected official saver has no stable public per-thread `keep_last=N` prune API and checkpoint blobs may be shared by channel version. It also does not add an archive service. Retention changes remain settings-only and require an integration test.

Every post-node checkpoint is measured using the saver serializer and must be at most 1 MiB. The expected CountyFlow state is materially smaller. An oversized state fails closed before registry promotion and before the next node.

## 19. Performance acceptance

The real Redis integration benchmark performs at least 20 sequential checkpoint writes and 20 exact reads against the pinned Docker runtime. It records:

- write minimum, average, P95, and maximum latency;
- read minimum, average, P95, and maximum latency;
- serialized checkpoint size average and maximum;
- Redis server/image and saver package versions.

V2-C sets no new formal checkpoint-latency redline. The run must record actual minimum/average/P95/maximum values, have zero operation errors, remain within the 1 MiB state-size guard, and preserve the already accepted Locust hard metrics and worker-recovery SLA. A material graph slowdown is reported with evidence rather than hidden behind a synthetic pass.

## 20. TDD and integration evidence

The mandatory V2-C tests are implemented with these exact test names:

1. `test_thread_registry_create`
2. `test_thread_id_stable_across_worker_retry`
3. `test_checkpoint_after_node`
4. `test_checkpoint_payload_serializable`
5. `test_checkpoint_excludes_dependencies`
6. `test_checkpoint_history_append_only`
7. `test_current_checkpoint_pointer`
8. `test_state_version_increments`
9. `test_terminal_thread_marked`
10. `test_resume_from_latest_checkpoint`
11. `test_resume_does_not_repeat_completed_nodes`
12. `test_resume_no_duplicate_dispatch`
13. `test_resume_no_duplicate_audit`
14. `test_checkpoint_registry_partial_failure`
15. `test_checkpoint_reconciliation`
16. `test_thread_read_api`
17. `test_thread_history_api`
18. `test_production_runtime_api_requires_auth`
19. `test_checkpoint_event`

Each behavior follows `RED -> confirm failure -> GREEN -> REFACTOR -> regression`. Fake/unit evidence uses `InMemorySaver`, fake repositories, deterministic counting nodes, and SQLite/MySQL-compatible metadata models. Real evidence uses the pinned official saver against Docker Redis 8.

The real crash test is process-level, not a mock exception:

1. start the nine-service Docker runtime with two workers;
2. submit the accepted core task;
3. hold or terminate Worker 1 immediately after a chosen canonical node-N event;
4. verify the stream item remains pending and record checkpoint N;
5. let the execution lock expire and Worker 2 claim the item;
6. verify `THREAD_RESUMED` references the same thread/checkpoint;
7. prove execution begins at N+1 through node counters/events;
8. assert one dispatch, one audit, no shared-memory mutation, terminal `APPROVED`, target `national-102`, adopted `memory-rain-li`, decision `REROUTE`, and Pending `0`.

## 21. Docker lifecycle

Docker remains nine services: MySQL, Redis, Qdrant, Neo4j, migration, backend, two workers, and frontend.

The Redis service changes from `redis:7.4-alpine` to `redis:8.2.9-alpine`, which includes the Redis 8 JSON/search capability required by the saver. AOF remains enabled and the named volume is preserved. Before graph execution, the migration/startup path runs `AsyncRedisSaver.asetup()` idempotently and verifies the required indices. Health/acceptance additionally verifies `PING`, JSON/search capability, AOF, stream group behavior, event replay, locks, and checkpoint round-trip.

An in-place production Redis upgrade is not implied by the Docker-dev edit. Production rollout requires backup, compatibility staging, and rollback procedures outside this repository's local Docker acceptance.

## 22. Failure behavior

Checkpoint failures are not treated like optional Graph Memory failures. A graph cannot safely continue past a node whose durable recovery boundary is unknown.

- Redis save failure: stop before the next node, leave message pending, publish a safe `TASK_FAILED`/retryable error code, and retry through normal worker recovery.
- MySQL promotion failure: stop before the next node, leave the Redis checkpoint unexposed, and reconcile on the next worker.
- read-side Redis failure: return a normalized 503 without changing execution.
- expired checkpoint: return registry metadata with `checkpoint_available=false`; never fabricate current state.
- event publication failure: retain the durable MySQL event and continue according to existing event-degradation rules; later clients can rehydrate from the read API.

Errors contain normalized codes and safe summaries only. Redis URLs, credentials, driver exceptions, serializer byte dumps, and state payloads are not logged.

## 23. V2-D deferrals

The following are explicitly absent from V2-C:

- runtime state override or `graph.update_state`;
- checkpoint payload mutation or deletion by API;
- pause/resume commands exposed to users;
- `Command(resume=...)` supplied by API callers;
- jump-to-node, target-node mutation, rollback, or branch fork;
- runtime thread mutation lock acquisition;
- expected-version write API;
- human approval workflow or RBAC implementation;
- merge of Qdrant/Neo4j memory into checkpoint control;
- ChatMemory, LLMWiki, or CodeGraph runtime behavior;
- automatic archive service or complex checkpoint compaction.

## 24. Design self-check A-H

### A. Is full state stored in MySQL?

PASS: no. MySQL stores registry and append-only safe metadata only; full checkpoint payload and pending writes remain in Redis.

### B. Is `GraphDependencies` checkpointed?

PASS: no. Dependencies remain closure/runtime injection objects outside `DispatchGraphState`; a recursive serialization/dependency test enforces the boundary.

### C. Are Dispatch, Memory, and Thread versions mixed?

PASS: no. `Dispatch.version`, `SharedMemoryFact.version`, and `RuntimeThread.state_version` have separate owners, repositories, and expected-version meanings.

### D. Is custom polling used instead of native interrupt/resume?

PASS: no. Installed LangGraph 1.2.11 behavior was probed directly; static boundaries use native `interrupt_after`, recovery uses `input=None`, and future dynamic interruption uses native `interrupt()` plus `Command(resume=...)`.

### E. Is Runtime Override implemented?

PASS: no. No mutation endpoint, override service, state update, target-node change, or thread mutation lock is implemented in V2-C.

### F. Is the canonical current checkpoint defined?

PASS: yes. Only `runtime_threads.current_checkpoint_id`, advanced by MySQL compare-and-swap after Redis persistence, is canonical.

### G. Is partial checkpoint failure designed?

PASS: yes. Redis-success/MySQL-failure produces a noncanonical orphan and stops the next node; the reverse ordering is prohibited; bounded reconciliation handles one verified successor.

### H. Is worker-crash resume designed?

PASS: yes. Worker 2 reuses the same thread, reconciles the canonical pointer, invokes with `input=None`, starts at N+1, preserves idempotent business effects, and ACKs only after terminal durability.

## 25. Primary references

- LangGraph checkpoint interfaces and synchronous durability: <https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/checkpointers.mdx>
- Official Redis saver package and Redis module requirements: <https://pypi.org/project/langgraph-checkpoint-redis/>
- Redis saver dependency range for checkpoint 4.x: <https://github.com/redis-developer/langgraph-redis/blob/main/pyproject.toml>
