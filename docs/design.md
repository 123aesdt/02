# CountyFlow AI — Final V2 Design Baseline

## Purpose and scope

CountyFlow AI identifies logistics anomalies and produces auditable asynchronous dispatch decisions for county operations. This final V2 baseline specifies a modular monolith with separately deployable API and dual-worker processes. It deliberately excludes microservices, RPC, Kubernetes, a distributed trace platform, and extra model vendors.

## System architecture

```text
React Console ──HTTP/WebSocket──> FastAPI API ──XADD──> Redis Streams
       ^                                  |                    |
       |                                  v                    v
       +──── state query / event fanout ─ MySQL <── Worker-1 / Worker-2
                                             ^                 |
                                             |                 v
                         Shared Memory Control Plane      LangGraph (8 agents)
                                             ^                 |
                        Qdrant Vector Memory ─┼─────────────────┤
                         Neo4j Graph Memory ──┘                 |
                                                 AsyncRedisSaver Checkpoint
                                                   + Thread Registry
                                                   + Runtime Override
```

FastAPI owns request admission, query APIs, task creation, task-event WebSocket delivery, and health endpoints. It must not run a complete graph in the request lifecycle. The two workers own stream consumption, retry and recovery, graph orchestration, and terminal persistence. MySQL records business facts and is the Shared Memory Control Plane; Qdrant owns semantic vector memory; Neo4j owns bounded relationship memory; Redis holds streams, ephemeral coordination, thread registry, and official AsyncRedisSaver checkpoints. Runtime Override mutates only allowlisted checkpoint state through the control boundary.

### Module boundaries

```text
backend/app/
  api/            request schemas, REST, WebSocket
  agents/         eight agent adapters; only application ports
  graph/          typed state and graph assembly
  providers/      LLM, embedding, weather/road interfaces and adapters
  memory/         Qdrant Entity-Relation retrieval and evidence formatting
  streams/        publisher, consumer, retry, recovery, idempotency ports
  models/         SQLAlchemy mappings and Alembic migrations
  repositories/   transactional MySQL access
  services/       application use cases and transaction boundaries
  core/           settings, errors, logging, observability
```

`frontend/src` uses app routing, page modules, feature modules, components, services, hooks, types, and styles. Page code never calls a provider or Redis directly.

## UI concept and design system

### V2-F2 implemented role frontend

The React console is one white enterprise SPA. A Principal adapter normalizes the server-issued identity; a canonical navigation registry filters entries by permissions; a landing resolver sends Dispatcher, Supervisor, Operator, Auditor, and Admin to `/workspace`, `/supervisor`, `/operations`, `/audit`, and `/overview`. Role affects default context and information order, while permissions affect actions and visibility. FastAPI remains the authorization boundary.

Local/docker-dev role preview obtains an allowlisted signed development session from the backend. It is absent from production compilation and rejected by the production runtime. Dispatcher cannot Override, Supervisor can perform eligible Runtime Intervention, Operator has no business write, Auditor is read-only, and Admin receives complete legitimate navigation without an IAM implementation.

The canonical light tokens and shared primitives cover the App Shell, Sidebar, Topbar, cards, tables, forms, dialogs, Graph, and Monitoring. API-mode gaps render explicit empty/not-exposed/unavailable/forbidden states instead of static KPI or Demo fallback. Existing Graph Memory, Shared Memory, Runtime Thread, Checkpoint, Runtime Override, Monitoring, and Security Audit behavior is preserved. Browser evidence and the page QA ledger live under `docs/verification/frontend-role-ui/`.

### Information architecture

| Navigation | Primary job | Main interaction |
| --- | --- | --- |
| 总览 | View operational health | Open anomaly or dispatch detail |
| 异常中心 | Triage anomalies | Filter, inspect, start dispatch |
| 智能调度 | Explain one decision | Follow eight nodes and compare routes |
| 运单管理 | Find orders | Table search and detail drawer |
| Agent 中心 | Monitor agents | Inspect latency, success rate, current task |
| 记忆中心 | Inspect long-term and shared memory | Query vector/graph evidence, inspect shared-memory versions and usage |
| 系统监控 | Observe runtime | Inspect stream, group, pending, dual workers, stores, checkpoints and override audit |

The Dashboard has compact logistics KPIs, a route situation map, recent-anomaly table, compact stream/workers/QPS/P95 health strip, and an Agent event feed. The anomaly and order centers are table-first, with sticky headers, column filters, row selection, and detail drawers; they are not card grids.

The Intelligent Dispatch detail page is a three-column workspace: left is anomaly/order/driver/vehicle and original route; center is environment risk, candidate-route comparison, recommended route, decision reason, vector/graph evidence, shared-memory projection, fallback, checkpoint and runtime-override outcome; right is a vertical graph run. The right column displays Intake, Entity Memory, Graph Memory, Environment, Capacity, Routing, Dispatch, and Audit with `waiting`, `running`, `success`, `fallback`, or `failed` status. A node has timestamp, latency, concise output, and an error/fallback explanation when applicable.

### Tokens

| Category | Token | Rule |
| --- | --- | --- |
| Base | `#080B10` | App canvas; never pure black |
| Surface | `#0D121A`, `#121923` | Two elevation levels, not nested cards |
| Borders | `rgba(210,224,240,.12)` | 1px, visible but understated |
| Text | `#EAF0F7`, `#9AA8B8` | Cold white primary, soft gray secondary |
| Status | teal `#35C6B0`, violet `#8D87FF`, amber `#E9AE55`, red `#D8676E` | Teal operational success; violet only AI/memory |
| Typography | Inter / PingFang SC | 28/34 page title, 18/26 panel title, 14/20 body, 12/16 meta; tabular figures |
| Spacing | 4px base | Primary rhythm 8, 16, 24, 32; page gutter 24 at 1440px |
| Radii | 6, 10, 14px | Controls 6, panels 10, large map/drawer 14 |
| Elevation | border plus `0 10px 30px rgba(0,0,0,.18)` | Use only floating drawer/menu; panels have no heavy shadow |

Use Lucide outline icons (16/18/20px), never emoji. Tables use a 40px header and 48px rows, left-aligned text, right-aligned numerical values, subdued row separators, hover surface shift, and teal selected state. Charts use teal for primary series, violet for memory/AI, amber/red only for warnings/errors, labeled axes and tooltip values. Do not rely on color alone for status.

Motion is 160–220ms opacity/transform for page and stream additions, 220ms color/background transition for graph state, and 500ms maximum numeric easing. All motion honors `prefers-reduced-motion`; no constant pulses or dominant glow. At 1366×768, the map/workflow preserve usable height and secondary dashboard panels collapse below; at 1440/1920, the dispatch detail remains a three-column layout.

## Data model

MySQL entities: `Order`, `AnomalyTicket`, `DispatchTask`, `Dispatch`, `DispatchCandidate`, `Driver`, `Vehicle`, `Route`, `AgentRun`, `AuditRecord`, and `IdempotencyRecord`. `Dispatch` contains `version` controlled by SQLAlchemy `version_id_col`; `DispatchTask` records task state and idempotency key. `AgentRun` and task events form the durable audit trail. Store monetary/distance quantities in `Decimal`-mapped columns.

Primary relations: Order has anomalies and dispatch tasks; an anomaly belongs to an order/driver/vehicle/route; a dispatch task has one terminal decision and many candidate routes/agent runs; a dispatch changes an assigned driver/vehicle/route and is versioned; audit references dispatch task and result.

## Typed LangGraph state and nodes

`DispatchGraphState` is a Pydantic/dataclass typed contract, not an `Any` bag. Required fields: `task_id`, `order_id`, `driver_id`, `vehicle_id`, `route_id`, `anomaly_type`, `anomaly_description`, `weather`, `road_condition`, `capacity_state`, `memory_results`, `candidate_routes`, `recommended_route`, `decision`, `decision_reason`, `fallback_used`, `fallback_reason`, `dispatch_version`, `audit_result`, `started_at`, and `completed_at`. Structured nested types describe weather/road risk, capacity, recalled memory, route candidates, and audit result.

```text
Intake → Entity Memory → Environment → Capacity → Routing → Dispatch → Audit
```

| Node | Input | Output | Failure action |
| --- | --- | --- | --- |
| Intake | task and anomaly | validated normalized context | terminal validation failure |
| Entity Memory | driver, route, anomaly | ranked memory evidence | empty evidence, continue |
| Environment | route and time | weather/road risk | static-rule fallback |
| Capacity | driver, vehicle, site | capacity state | terminal unavailable-capacity state |
| Routing | context, risk, capacity, memory | candidates/recommendation/reason | manual-review decision |
| Dispatch | recommendation and version | durable dispatch result/version | conflict/retry or manual review |
| Audit | complete state | accepted/manual-review/rejected audit | terminal manual review |

Agents consume ports such as `LLMProvider`, `EntityMemoryPort`, `EnvironmentPort`, `CapacityPort`, and `DispatchService`; graph construction injects implementations. No node imports infrastructure SDKs.

## Redis Streams, recovery, and idempotency

The API creates a MySQL `DispatchTask` in `queued` state, derives/validates an idempotency key, then XADDs `{task_id,idempotency_key,attempt}` to `dispatch:tasks`. A named group (`dispatch-workers`) uses `XREADGROUP`; each worker has an instance-specific consumer name. On success, the worker commits terminal task/dispatch/audit data, publishes a task event, then XACKs. It must not ACK before durable state.

On startup and periodically, each worker uses `XAUTOCLAIM` for messages idle beyond a configured reclaim threshold, increments the durable attempt counter, and either processes or sends exhausted messages to `dispatch:dead-letter` with the failure class. Retriable failures use bounded exponential backoff with jitter; validation, confirmed conflict, and audit rejection are not hidden retries. Cancellation stops reads, finishes or releases work safely, and never swallows `asyncio.CancelledError`.

Idempotency is enforced in MySQL with a unique `idempotency_key` and task/dispatch unique constraints, with Redis `SET NX EX` as a short-lived contention guard. A duplicate API request returns the existing task. A recovered or retried worker reads the durable task state; terminal tasks only emit an idempotent status event, never write a second dispatch.

Redis checkpointer is restricted to resumable LangGraph checkpoints; it does not replace MySQL task/dispatch truth. Redis task-event channels/streams power WebSocket fanout; reconnecting clients rehydrate from MySQL and replay events after `last_event_id`.

## V2-C persistent checkpoint and thread state foundation

V2-C makes the existing eight-agent graph resumable without changing its topology or routing rules. The official asynchronous Redis checkpointer stores immutable LangGraph checkpoint payloads and pending writes. The existing Redis service is upgraded to a pinned Redis 8 image so RedisJSON and RediSearch are available; no tenth Docker service is added. MySQL stores only a lightweight one-task/one-thread registry, the canonical `current_checkpoint_id`, a monotonic `state_version`, and append-only safe lifecycle metadata.

Every successful node boundary uses synchronous checkpoint durability before the MySQL pointer is promoted. Redis-first/MySQL-second ordering prevents the registry from pointing at a checkpoint that was never written. A Redis success followed by a registry failure leaves a noncanonical orphan; the worker stops before the next node and a bounded reconciler may promote only the single verified next checkpoint. Worker recovery reuses the server-derived `thread_id` and resumes with `input=None` from the exact canonical checkpoint, so completed nodes do not run again.

`DispatchGraphState` remains a typed, JSON-serializable value contract. It contains only safe node-boundary metadata in addition to existing business fields; clients, sessions, repositories, services, locks, and checkpointers stay in runtime dependency injection. Qdrant and Neo4j remain long-term memory stores and never hold runtime state.

Optional GET-only runtime-thread endpoints and a read-only dispatch-detail panel expose bounded current/history views. The router is feature-gated, and production configuration rejects enabling it without an authorization provider. V2-C does not expose pause, resume command, rollback, `update_state`, checkpoint mutation, target-node mutation, or any Runtime Override behavior; those remain V2-D work. The full protocol, schema, failure matrix, retention, performance budget, and test mapping are defined in `docs/superpowers/specs/2026-08-27-v2-c-checkpoint-design.md`.

## V2-D1 safe-boundary runtime override

V2-D1 designs a write path for one controlled runtime field: canonical `Vehicle.status` before Capacity. It does not expose arbitrary state patches. The only allowed transitions are `NORMAL -> BROKEN`, `NORMAL -> UNAVAILABLE`, and `NORMAL -> MAINTENANCE`, and the only allowed boundary is a promoted Environment checkpoint whose unchanged next node is Capacity. `BROKEN -> NORMAL`, other entities/fields, historical checkpoint selection, rollback, skip, goto, terminal reopen, and a frontend action control remain deferred.

Worker and Override share `countyflow:lock:thread:{thread_id}` as a short boundary lease. Workers execute one native `interrupt_after` node segment at a time: under the lease they reload the canonical row and CAS `STABLE -> RUNNING`, release the lease before node execution, persist the node checkpoint to Redis, and promote it back to `STABLE`. Override reserves an expiring durable intent, acquires the same lease, reloads `STABLE`, and validates the exact pointer/version before mutation. If Worker claims first, Override returns `THREAD_NOT_STABLE`; if Override owns first, Worker cannot claim Capacity until the override result is canonical. The API never waits indefinitely for a boundary.

The client supplies `idempotency_key`, entity/field, old/new values, reason, `expected_version`, and an optional `expected_next_node` precondition. The server generates `override_id` and derives `operator_id`, role, and permissions from the existing management authorization provider. Writes require `runtime:override`; reads require `runtime:read` or the existing equivalent. Enabling production writes without an injected external provider fails closed, and `human_confirmed` is never treated as authorization.

State mutation uses LangGraph 1.2.11's official asynchronous `aupdate_state` with the exact canonical config and `as_node=current_node`. The returned checkpoint must be a direct child of the source, remain in the empty namespace, preserve `last_completed_node`, `completed_node_count`, and next node, change only `vehicle_status`, remain JSON serializable, and satisfy the existing byte limit. No code edits saver JSON or Redis checkpoint keys. Capacity consumes `state.vehicle_status` directly and marks `BROKEN`, `UNAVAILABLE`, or `MAINTENANCE` vehicles unavailable; Routing remains unaware of override and consumes normal Capacity output.

MySQL adds one durable command ledger and one append-only attempt ledger. Canonical promotion remains Redis-first/MySQL-second and CASes `(source_checkpoint_id, expected_version, STABLE)` to the result checkpoint and `state_version + 1`; override does not increment the completed-agent `checkpoint_count`. The same transaction finalizes `APPLIED` and appends the runtime event. Canonical reads continue using only the MySQL pointer.

If Redis succeeds but MySQL promotion does not, the result is a noncanonical override orphan and the command becomes or remains `PARTIAL`; Worker resume is blocked. `RuntimeOverrideReconciler` may inspect only the explicit result checkpoint stored for that override and may promote it only when it is the validated direct successor and the original pointer/version are still current. It never selects Redis “latest.” A real version advance yields `CONFLICT` and preserves the orphan for normal retention.

Audit records actor, time, thread, source/result checkpoint, expected/observed/final version, entity/field, old/new value, reason, decision, status, safe error, and per-stage timings. Requested/applied/rejected/conflict/partial events carry bounded summaries and use logical event idempotency. Runtime override does not automatically modify MySQL shared-memory facts, Qdrant, or Neo4j; an optional `MEMORY_UPDATE_SUGGESTED` event is advisory only.

The write API is `POST /api/v1/runtime/threads/{thread_id}/overrides`; safe status/history reads use `/api/v1/runtime/overrides/{override_id}` and a bounded per-thread list. D1 keeps the frontend read-only. Full schemas, race proof, failure windows, reconciliation rules, performance measurements, and test mapping are defined in `docs/superpowers/specs/2026-08-27-v2-d1-runtime-override-design.md`.

## V2-D2 Runtime Intervention Workbench

V2-D2 exposes the V2-D1 safe override through the existing `/dispatch/:taskId` detail workspace. It preserves the three-column layout: the existing task, memory, environment, Capacity, routing, dispatch, and audit evidence remain in the left/center columns; the right column composes Runtime Thread, Runtime Intervention, bounded Override History, and an ordered Agent/Runtime Timeline. It does not add a separate administration system or redesign the console theme.

The backend owns intervention eligibility. A read-only intervention context combines the canonical MySQL thread pointer, the exact Redis checkpoint, and the existing authorization provider, then returns one of `ELIGIBLE`, `NOT_STABLE`, `TERMINAL`, `NO_PERMISSION`, `WRONG_BOUNDARY`, or `BUSY`. The browser never infers permission from a visible button and never duplicates D1 policy. POST still repeats authorization and every D1 precondition.

The UI exposes only `Vehicle.status`, with `NORMAL -> BROKEN | UNAVAILABLE | MAINTENANCE`. Opening the confirmation dialog freezes the thread ID, canonical checkpoint, state version, next node, entity, field, and old/new values. Later WebSocket/refetch changes mark the dialog stale and disable Confirm; the captured preconditions are never silently replaced. A first Confirm creates one idempotency key, and network retry reuses it. Closing and starting a new intervention creates a new key.

HTTP responses and authenticated override/thread GETs are the business truth. Existing task-event WebSocket delivery provides requested, applied, rejected, conflict, and partial notifications and triggers coalesced refetch. Override history is newest-first and bounded, and displays only actor, reason, safe transition, status, versions, and checkpoint identifiers. It excludes authorization material, idempotency fingerprints, and checkpoint payloads.

Capacity feedback is projected from the real `CAPACITY_COMPLETED` event and shows the canonical vehicle status, availability, capacity result, risk, and safe reason. Routing remains unaware of override mechanics and the page presents its real outcome. An override may therefore end in `REVIEW_REQUIRED`; the ordinary no-override regression remains `memory-rain-li -> national-102 -> REROUTE -> APPROVED`.

API mode never falls back to mock intervention data. The V2-D2 acceptance used Playwright against the then-current nine-service Docker runtime and covered success, stale dialog, concurrent browsers, forbidden access, and terminal tasks. Runtime data refresh is event-driven plus necessary HTTP refetch; no high-frequency runtime polling is introduced. Pause, Resume, rollback, goto, skip, rerun, arbitrary state mutation, reverse vehicle transition, and shared-memory mutation remain deferred. Full UX states, DTOs, event fields, browser orchestration, and test mapping are defined in `docs/superpowers/specs/2026-08-27-v2-d2-intervention-workbench-design.md`.

## Optimistic lock

`Dispatch.version` uses SQLAlchemy mapper `version_id_col` and a non-null integer generator. Mutations load a dispatch in a transaction; SQLAlchemy emits version-qualified update statements. `StaleDataError` rolls back and becomes a domain `DispatchConflict`, returned by the API as HTTP 409 with current version and a retry/reload action. Concurrency tests use two independent sessions reading version 5, commit A to 6, then prove B fails with `StaleDataError`; no Python precheck is accepted as the lock.

## Entity-Relation memory

Qdrant collection `entity_resolution_memory` stores a real embedding vector generated from normalized DriverID, RouteID, AnomalyType, and ResolutionText. Payload includes `memory_id`, `driver_id`, `route_id`, `anomaly_type`, `resolution_text`, `metadata`, `usage_count`, `success_count`, `created_at`, and embedding model/version. Entity Memory filters only where business-scoping requires it but always performs vector similarity search and returns top results with score. The routing reason includes selected evidence text and similarity, e.g. 李师傅雨天经过新平路容易湿滑，历史建议改走 102 国道.

## V2-A Neo4j Graph Memory

V2-A adds Neo4j Community as a second, complementary memory layer. Qdrant continues semantic Top-K case recall; Neo4j stores allowlisted entities, explicit relations, and bounded one-to-three-hop paths. MySQL remains the source of truth and Neo4j never represents a running LangGraph checkpoint.

The graph repository protocol separates Cypher and driver transactions from `GraphMemoryService`. A deterministic extractor produces stable candidate entities and only input-supported relations. Labels and relationship types come from enums; all values are parameters. Schema bootstrap creates an idempotent global entity-key constraint plus entity ID/type indexes, and the development seed is repeatable.

The V2-A topology is:

```text
Intake → Entity Memory → Graph Memory → Environment → Capacity → Routing → Dispatch → Audit
```

`GraphDependencies` injects the service. State adds only serializable facts, paths, usage, safe error, and timing fields. Known graph-store failures emit a degraded event and continue the V1 pipeline. Routing rules remain unchanged; graph facts are evidence only. Audit persists compact graph summaries. Full schemas, seed facts, security rules, failure behavior, and deferred Merge/Override boundaries are defined in `docs/memory_spec.md`.

## Provider and resilience contracts

`LLMProvider` exposes async structured completion with model and timeout configuration. `EmbeddingProvider` exposes async `embed(texts) -> vectors`. `OpenAICompatibleLLMProvider` and `OpenAICompatibleEmbeddingProvider` are the only initial production adapters; they each accept independent base URL, API key, and model. `FakeLLMProvider` and `FakeEmbeddingProvider` are test-only. Settings use separate `LLM_*` and `EMBEDDING_*` variables; keys are never logged.

Weather and road ports use `httpx.AsyncClient` with an approximately 0.8s timeout, normalized error types, and a per-provider circuit breaker. Timeout/open circuit/invalid provider response selects a versioned static route rule and records `fallback_used`, `fallback_reason`, and `elapsed_ms`. The caller continues in under one second; fallback is visible in the graph, audit, API, and UI.

## WebSocket

`/ws/tasks/{task_id}` authenticates and authorizes task visibility, sends a snapshot first, then ordered events containing `event_id`, `type`, `occurred_at`, `agent`, `status`, and safe payload. The UI reconnects with last event id; the API reads durable state first and then subscribes to Redis fanout. Slow sockets have bounded buffers and receive a resync signal rather than blocking workers.

## Deployment and performance plan

Compose has eleven services: frontend, backend, two workers, migration, Redis 8, MySQL 8, Qdrant, Neo4j Community, Prometheus, and Grafana. Migration is one-shot, leaving ten long-running services. Stateful stores use named volumes and health checks. Backend and workers wait on health/migration completion; workers use `restart: unless-stopped`. `.env` feeds secrets.

Locust scenarios: order list/detail, anomaly list/bulk list, task status, concurrent dispatch submission, plus query-only baseline separated from LLM latency. Acceptance targets are QPS ≥200, P95 <300ms, error rate <0.1%; good ≥500 and excellent ≥1000. Results are recorded only from executed runs.

## Test strategy and acceptance mapping

Unit tests cover typed state, interfaces, input normalization, static fallback, retry classification, and decision evidence with fake providers. Integration tests run against real Redis/MySQL/Qdrant containers for stream publish/group/ACK, pending recovery, idempotency, vector recall, and version locking. API/WebSocket tests cover status and event ordering. End-to-end Compose tests run a submitted anomaly through a worker. Required first tests are `test_memory_recall`, `test_sqlalchemy_optimistic_lock`, and `test_api_degradation`; subsequent tests include stream, group, retry, idempotency, pending recovery, graph state, and dispatch flow.

## V2-G1 production observability architecture

V2-G1 is a metrics-first operational layer and does not modify the eight-agent topology or any Routing, Dispatch, Shared Memory, Graph Memory, Checkpoint, Runtime Override, or audit decision. Backend, Worker-1, and Worker-2 each own a process-level Prometheus registry and expose `/metrics` on internal container port 9100. Prometheus scrapes those three targets; Grafana reads Prometheus through provisioned dashboards. Neither metrics endpoint nor Prometheus is published as a product API.

```text
Backend:9100/metrics ─┐
Worker-1:9100/metrics ├─> Prometheus ─> Grafana
Worker-2:9100/metrics ┘        │
                               └─> ObservabilityReadService
                                      └─> typed, authorized FastAPI endpoints
                                             └─> existing Frontend Monitoring
```

Compose grows from nine to eleven services by adding only Prometheus and Grafana. Prometheus retains seven days in a named volume and remains internal. Grafana is host-accessible through a configured port and uses repository-provisioned datasource/dashboard files plus environment-owned credentials. Alertmanager, exporters, Loki, Tempo, Jaeger, OpenTelemetry Collector, and outbound notification channels remain deferred.

All application metric labels come from a fixed allowlist. Task, thread, order, dispatch, memory, mutation, override, checkpoint, driver, vehicle, route, user, operator, raw-path, exception-text, and reason values never become labels. Those safe identifiers may appear in structured logs and audit correlation. Metrics are best-effort side effects behind a narrow recorder; registry or recording failure cannot change a business transaction, graph result, checkpoint, message ACK, retry, or degradation path.

Browsers never query Prometheus or execute arbitrary PromQL. A fixed-query `ObservabilityReadService` maps Prometheus responses into typed DTOs for summary, agents, workers, memory, runtime, and dependency endpoints. Reads require `monitor:read` from the request-scoped authenticated principal; production fails closed without valid OIDC/JWT configuration. The existing Monitoring page gains explicit LIVE, STALE, UNAVAILABLE, and NO_PERMISSION states while retaining a visually separate VERIFIED ACCEPTANCE BASELINE section.

Structured JSON logs in docker-dev/production carry safe request/correlation, task, thread, agent, event, error-code, and duration fields. Local mode may remain human-readable. A future tracing implementation may reuse those correlation attributes, but G1 adds no tracing SDK or backend. The complete metric catalog, buckets, cardinality rules, SLO windows, PromQL, alert guards, security boundaries, and failure behavior are defined in `docs/observability_spec.md`, `docs/slo.md`, and `docs/superpowers/specs/2026-08-28-v2-g1-observability-design.md`.

## V2-G2 security architecture

V2-G2 adds one authentication and authorization control plane without changing the asynchronous business path or any agent decision algorithm. Docker development uses signed short-lived development JWTs; production accepts only the validated OIDC/JWKS path. `AuthenticatedPrincipal` is request-scoped and is passed explicitly into Runtime Thread, Runtime Override, Observability, Shared Memory, Dispatch, and Security Audit boundaries. Legacy process-global trusted authorizers and configuration switches are absent.

The docker-dev browser no longer exposes a manual token-login form. It obtains a short-lived development session through a local/docker-dev-only bootstrap route and keeps the resulting bearer token in page memory. The route is unavailable outside `local` and `docker-dev`; production remains OIDC-only and fail-closed.

The server owns the role-permission matrix and actor identity. HTTP admission returns 401 for authentication failures, 403 for missing permission, 429 with `Retry-After` for bounded Redis rate limits, and bounded 503 errors when required security controls are unavailable. Task WebSockets require an authenticated ticket-issuance request followed by exact-task, expiring, atomic single-use ticket consumption. Browser guards are UX only; every direct API request is independently enforced by FastAPI.

Security audit records are append-only to application roles and readable only through the bounded `audit:read` projection. Logs, metrics, errors, tickets, DTOs, and browser URLs exclude tokens and secret material. Prometheus labels remain low-cardinality. `.env` and `.docker.env` stay ignored, examples contain no secret values, and production cannot select development authentication.

The real Docker acceptance preserves 11 declared services. Neo4j password initialization runs only for a fresh `/data` volume; an initialized volume skips the repeated initial-password JVM while keeping database authentication and the existing credential active. This prevents restart-time corruption without deleting or resetting graph data.

## Self-review

The final V2 design maps the implemented requirements to modules, tests, and retained verification evidence, avoids preemptive microservices and vendor proliferation, and makes the key tradeoffs explicit.
