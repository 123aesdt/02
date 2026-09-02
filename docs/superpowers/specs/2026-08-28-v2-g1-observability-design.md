# CountyFlow V2-G1 Production Observability Design

**Status:** DESIGN READY — implementation requires explicit approval  
**Date:** 2026-08-28  
**Scope:** Metrics-first production observability, structured-log correlation, SLOs, Prometheus, Grafana, and the existing Frontend Monitoring page. No business algorithm changes.

## 1. Frozen baseline and goals

V2-G1 preserves the accepted CountyFlow path:

```text
Frontend → FastAPI → Redis Streams → Worker-1 / Worker-2
         → Intake → Entity Memory → Graph Memory → Environment
         → Capacity → Routing → Dispatch → Audit
```

Qdrant remains Vector Memory, Neo4j remains Graph Memory, MySQL remains the Shared Memory Control Plane, and Redis remains Streams/Event/Lock/AsyncRedisSaver infrastructure. Routing, Dispatch, Graph Memory, Shared Memory, Checkpoint, Runtime Override, audit, and failure-degradation semantics are frozen.

The G1 goal is to detect operational degradation before users report it, localize the affected subsystem, and evaluate approved operational SLOs without making observability part of the business success path.

## 2. Existing observability audit

| Capability | Current evidence | G1 decision |
|---|---|---|
| Prometheus Python client | Not present in `backend/pyproject.toml` | Add one production dependency during implementation |
| `/metrics` or metrics HTTP server | Absent | Add one internal endpoint per Backend/Worker process |
| Prometheus / Grafana | No repository directories or Compose services | Add exactly two services |
| Backend process model | Dockerfile starts one Uvicorn process; no `--workers` | Use one process registry; document multiprocess migration |
| Worker HTTP surface | Worker is an asyncio loop without FastAPI | Add only a lightweight metrics server, not another application |
| Health | `/health` returns safe runtime configuration; Compose has real service healthchecks | Preserve `/health`; add bounded application probes outside request paths |
| Live dependency health | Frontend shows `CONFIGURED` or `NOT EXPOSED`, not real probes | Add dependency gauges and typed read DTOs |
| Logging | Standard-library worker logger exists; no global structured configuration | Add JSON formatting and correlation context without Loki |
| Correlation | `task_id` and `thread_id` exist; no request/correlation ID crosses the full path | Add one bounded `correlation_id`, reusing existing IDs rather than replacing them |
| Frontend Monitoring | Existing page reads `/health`; API mode does not fall back to Mock | Incrementally add live observability hooks and retain strict mode isolation |
| Verified Acceptance | Existing `VerifiedBaselinePanel` correctly labels non-live evidence | Preserve unchanged and visually separate from Live |
| Acceptance metrics helper | `backend/app/acceptance/metrics.py` calculates offline evidence | Keep separate; it is not a live metrics registry |
| Tracing | No OTel SDK/backend | Define correlation boundary only; defer tracing infrastructure |

## 3. Architecture options

### Option A — Prometheus + Grafana + Backend Read API (selected)

```text
Backend:9100/metrics ─┐
Worker-1:9100/metrics ├─> Prometheus ─> Grafana
Worker-2:9100/metrics ┘        │
                               └─> ObservabilityReadService
                                      └─> typed FastAPI read API
                                             └─> Frontend Monitoring
```

This provides standard scraping and operations dashboards while keeping PromQL, credentials, topology, and unbounded responses away from browsers. It reuses the current Monitoring page and existing management-authorization pattern.

### Option B — Browser reads Prometheus directly (rejected)

This exposes query construction, CORS, topology, and potentially sensitive series metadata to browsers. It also prevents a stable CountyFlow DTO and makes authorization depend on Prometheus configuration.

### Option C — Grafana only (rejected)

Grafana is appropriate for operations and engineering, but it does not replace the supervisor-facing Monitoring page. Removing the product read model would regress V2-F and make Grafana an accidental product dependency.

## 4. Metrics, logs, traces, and audit

| Signal | Purpose | Cardinality | G1 implementation |
|---|---|---|---|
| Metrics | Aggregated trends, SLOs, alerts | Strictly bounded | Primary scope |
| Structured logs | Per-event diagnosis and correlation | May contain safe IDs | JSON in docker-dev/production; human-readable local mode |
| Traces | Cross-process span timing | Safe correlation attributes | Boundary only; SDK/backend deferred |
| Audit | Non-repudiable business facts | Business identifiers allowed | Existing durable audit remains authoritative |

None replaces another. Metrics never contain prompts, memory text, route descriptions, raw exceptions, headers, credentials, or entity identifiers.

## 5. Metrics serving and registry lifecycle

- Backend, Worker-1, and Worker-2 each expose `/metrics` on container port `9100`.
- Port `9100` is not published to the host. Prometheus reaches it only through `countyflow_internal`.
- `prometheus_client.start_http_server` is acceptable because workers do not need a second FastAPI app. Backend uses the same small server for a uniform security boundary.
- Each OS process owns one `CollectorRegistry`, one metric catalog, one recorder, and one HTTP server lifecycle.
- `create_app()` and runtime factories accept an injected recorder/runtime. Repeated test app factories use isolated registries and cannot duplicate-register metric families.
- `NoOpMetricsRecorder` is the default when metrics are disabled. `SafeMetricsRecorder` catches instrumentation failures and never changes the wrapped business return, exception, transaction, ACK, or checkpoint outcome.
- Current Docker Backend is one Uvicorn process. G1 supports that verified model. If a deployment selects more than one Uvicorn worker, startup must require `PROMETHEUS_MULTIPROC_DIR` and the Prometheus multiprocess collector, clear the directory before the parent starts, and use multiprocess-compatible gauge modes. Until that adapter is implemented and tested, `METRICS_ENABLED=true` with multiple Backend processes fails fast rather than publishing incomplete data.

## 6. Metrics abstraction and instrumentation points

`app.observability` owns the vendor client. Business modules consume a narrow `MetricsRecorder` protocol with methods such as:

```python
class MetricsRecorder(Protocol):
    def observe_http(self, method: str, route_template: str, status_class: str, seconds: float) -> None: ...
    def observe_agent(self, agent: str, result: str, seconds: float) -> None: ...
    def observe_operation(self, subsystem: str, operation: str, result: str, seconds: float | None = None) -> None: ...
    def set_state_count(self, metric: str, result: str, count: int, *, store: str | None = None) -> None: ...
    def increment_invariant(self, reason_code: str, *, store: str | None = None) -> None: ...
```

The concrete facade maps bounded inputs to the metric catalog; arbitrary metric names are not accepted by production call sites. Focused adapters (`HttpMetrics`, `AgentMetrics`, `MemoryMetrics`, `RuntimeMetrics`, `WorkerMetrics`, `DependencyMetrics`) may sit behind the facade to keep files single-purpose.

Instrumentation locations:

- HTTP: one FastAPI middleware uses the matched route template after routing, not `request.url.path`.
- Agents: extend the existing centralized `_instrument_node` wrapper in `graph/builder.py`; do not duplicate timers in eight node files.
- Vector/Graph/Environment: service boundaries classify hit/miss/degraded/error using bounded enums.
- Shared Memory/Override: record only after the authoritative result is known; metrics never participate in a transaction.
- Checkpoint: instrument `RedisRuntimeCheckpointStore` and canonical promotion/resume/reconciliation boundaries.
- Worker: instrument process, read/process/ACK/retry/recover/DLQ results in `DispatchWorker` and queue summaries.
- WebSocket: increment/decrement active connections with `try/finally`; group events into six fixed families.
- Current-state gauges: a backend-owned `OperationalStateSampler` refreshes MySQL/Redis/store counts every 15 seconds with an 800 ms per-probe timeout. It runs outside request and business transaction paths. Failed samples retain no false zero; a corresponding dependency/probe result exposes staleness.

## 7. Cardinality contract

The only application label names are:

```text
method, route_template, status_class, agent, result, decision,
operation, dependency, worker, event_type, runtime_profile,
projection, store, reason_code
```

The catalog deliberately normalizes suggested conceptual labels to this allowlist:

- HTTP `route` becomes `route_template`.
- Graph `query_type`, Environment `provider`, Redis operation, and Checkpoint operation become `operation`.
- Lifecycle `status` becomes `result`.
- WebSocket `event_group` becomes bounded `event_type`.
- Application `error_code` becomes bounded `reason_code`; subsystem becomes `operation`.

Forbidden labels include `task_id`, `thread_id`, `order_id`, `dispatch_id`, `memory_id`, `mutation_id`, `override_id`, `checkpoint_id`, `driver_id`, `vehicle_id`, `route_id`, `user_id`, `operator_id`, `error_message`, free-form `reason`, and raw URL paths. A catalog contract test fails on any label outside the allowlist or any label value outside its enum.

## 8. Prometheus architecture

Repository-owned configuration lives under `monitoring/prometheus/`:

```text
prometheus.yml
rules/recording.yml
rules/alerts.yml
```

Prometheus scrapes `backend:9100`, `worker-1:9100`, and `worker-2:9100` every 15 seconds with a 5-second scrape timeout. Infrastructure exporters and direct vendor endpoints are intentionally omitted from G1: the four approved dependency probes provide the required health series without four more containers or vendor-specific cardinality. Retention is 7 days with a named `countyflow_prometheus` volume. Port 9090 was available during design audit but is not published by default.

Recording rules provide short stable queries for dashboards and the read service:

- `countyflow:slo:http_p95_5m`
- `countyflow:slo:http_error_ratio_5m`
- `countyflow:slo:http_qps_5m`
- `countyflow:slo:agent_p95_5m`
- `countyflow:slo:graph_p95_5m`
- `countyflow:slo:checkpoint_p95_5m`
- `countyflow:slo:override_success_ratio_15m`
- `countyflow:slo:worker_pending`
- `countyflow:slo:worker_stream_lag`

## 9. Grafana architecture

Grafana is provisioned from Git:

```text
monitoring/grafana/provisioning/datasources/prometheus.yml
monitoring/grafana/provisioning/dashboards/dashboard.yml
monitoring/grafana/dashboards/countyflow-v2-operations.json
```

`CountyFlow V2 Operations Overview` contains:

1. SLO Overview
2. API
3. Eight-Agent pipeline
4. Worker / Redis
5. Vector / Graph Memory
6. Shared Memory
7. Runtime Thread / Checkpoint
8. Runtime Override
9. Dependencies

Grafana reads only live Prometheus data. It never displays Top-1 98% or other acceptance fixtures as live series. Grafana is mapped to host port 3000 for operators; the port was available during design audit. Credentials come from `.docker.env`/environment, contain no repository default such as `admin/admin`, and are not returned by APIs. Grafana data uses a named `countyflow_grafana` volume; dashboards and datasources reappear after recreation without manual clicks.

## 10. SLO and alert model

Approved operational SLOs are API P95 `<300 ms`, API unexpected error rate `<0.1%`, Graph query P95 `<150 ms`, every Worker recovery `<=5 s`, Projection Leak `=0`, and Override downstream stale read `=0`. Acceptance values such as Top-1 98%, 15/15, and Locust 400.071 QPS are historical verified baselines, not rolling SLO measurements.

For live Worker recovery, the surviving Worker records the pending entry's Redis idle duration at recovery claim and adds claim-to-terminal-ACK elapsed time. This is the closest bounded online measurement and drives the `>5 s` breach counter. It must be named and documented as an observable estimate: only the real failure harness owns the exact external kill `T1` to durable recovered ACK `T6` acceptance measurement.

Prometheus alert rules include the required Backend/Worker/Dependency down, API latency/error, pending/lag, recovery breach, graph/checkpoint latency, partial mutation, override conflict, and invariant alerts. Rate alerts use `for` windows and minimum-traffic guards. Recovery uses `increase(countyflow_worker_recovery_slo_breaches_total[15m]) > 0`, never a sticky last-value gauge. Exact rules and non-SLO warning thresholds are defined in `docs/slo.md`.

Alertmanager and outbound notification channels are not part of G1. Prometheus evaluates rules and Grafana visualizes alert state.

## 11. Observability Read API

Browsers never call Prometheus. `ObservabilityReadService` owns a fixed query catalog and returns typed DTOs from:

```text
GET /api/v1/observability/summary
GET /api/v1/observability/agents
GET /api/v1/observability/workers
GET /api/v1/observability/memory
GET /api/v1/observability/runtime
GET /api/v1/observability/dependencies
```

All endpoints accept only `window=5m|15m|1h`; server-owned templates choose PromQL and step. There is no generic PromQL endpoint. The Prometheus adapter uses an explicit one-second timeout and validates response shape before mapping it into bounded DTOs.

DTO envelopes contain `state`, `as_of`, `window`, safe values/trends, and an optional configured Grafana URL. States are:

- `LIVE`: relevant newest sample is at most 45 seconds old.
- `STALE`: Prometheus responds but a required target/sample is 45–120 seconds old or a bounded subset is incomplete.
- `UNAVAILABLE`: Prometheus is unreachable, invalid, or required data is older than 120 seconds; API returns `503 OBSERVABILITY_UNAVAILABLE`.
- `NO_PERMISSION`: authorization fails; API returns 403.

Missing data remains `null`/unavailable and is never silently converted to zero.

## 12. Authorization and security

- The read API requires `monitor:read` through a narrow `ObservabilityAuthorizer` protocol modeled after the current runtime authorizer.
- docker-dev may use an explicit trusted adapter. Production with the API enabled and no injected external authorizer fails closed.
- The internal metrics port is not host-published. Metrics contain no credentials, raw headers, user text, IDs, prompts, memory content, routes, or reasons.
- Prometheus and Grafana failures cannot affect `/health`, dispatch submission, workers, graph execution, checkpointing, override, or persistence.
- Grafana URL is a safe optional setting, not hard-coded in frontend source.

## 13. Frontend Monitoring

The existing page is extended, not redesigned. It has two explicit regions:

### Live Observability

Current QPS, API P95, unexpected error rate, per-agent P95, Worker target/pending/lag, Graph P95, Checkpoint P95, Override applied/conflict, Memory PARTIAL, and dependency state. Time ranges are Last 5m, 15m, and 1h. Existing CSS/SVG capabilities render small trends; no large chart dependency is added.

The page distinguishes `LIVE`, `STALE`, `UNAVAILABLE`, and `NO_PERMISSION`. API mode uses only the observability API and never imports or invokes a Monitoring mock after failure.

### Verified Acceptance Baseline

The existing panel remains separate and immutable: Vector Top-1 49/50 (98%), Top-3 50/50, Graph Recall 20/20, Worker Recovery max 4.824s, 15-round 15/15, Locust min QPS 400.071, and P95 max 200ms. Every value remains labeled `VERIFIED ACCEPTANCE BASELINE`, not live telemetry.

Grafana remains an operator/developer deep-dive; CountyFlow Monitoring remains a supervisor-facing summary. An `Open Grafana` link appears only when an authorized safe URL is configured.

## 14. Structured logging and correlation

docker-dev and production use JSON with `timestamp`, `level`, `service`, `runtime_profile`, `request_id`, `correlation_id`, `task_id`, `thread_id`, `agent`, `event`, `error_code`, and `duration_ms`. Local mode may use human-readable output.

FastAPI accepts or generates a bounded correlation ID (ASCII `[A-Za-z0-9._-]`, maximum 64 characters), returns it as `X-Request-ID`, and stores it in a `ContextVar`. Dispatch messages add an optional backward-compatible `correlation_id`; Worker binds it while processing; graph state keeps only the safe string; TaskEvent exposes it as an optional top-level field; Audit persists it in existing evidence JSON. Existing `task_id` and `thread_id` remain unchanged.

High-cardinality IDs are allowed in safe logs/audit but never metric labels. API keys, authorization tokens, passwords, raw headers, `.env`, prompt text, and raw exception details remain prohibited.

Future OTel spans may use `request_id`, `task_id`, and `thread_id` as correlation attributes. G1 does not install the OTel SDK, collector, Tempo, or Jaeger.

## 15. Docker and failure isolation

Compose grows from 9 to 11 services by adding only `prometheus` and `grafana`. Migration remains one-shot Exited(0). Named volumes are `countyflow_prometheus` and `countyflow_grafana`. The full launcher reports both readiness states; the light local launcher remains unchanged.

Failure behavior:

- Recorder/registry failure: safe no-op; business result unchanged.
- Prometheus down: observability API 503 and frontend UNAVAILABLE; dispatch still succeeds.
- Grafana down: internal Monitoring continues because it reads Prometheus.
- Neo4j down: dependency gauge becomes 0; frontend shows DOWN; existing Graph Memory degradation continues.
- Worker-1 down: its target is down, Worker-2 stays up, and existing recovery continues.
- Sampler/probe failure: explicit unavailable/stale series; never false zero business data.

## 16. Test and acceptance strategy

TDD covers the required HTTP, route-template, cardinality, agent, Vector, Graph, Shared Memory, Checkpoint, Override, Worker, dependency, failure-isolation, registry lifecycle, read API, authorization, query allowlist, frontend state, and no-Mock contracts.

Real Docker acceptance proves all three targets UP, datasource provisioning, dashboard provisioning, live Monitoring, a real dispatch causing bounded metric changes, Neo4j failure/recovery, Worker-1 failure with Worker-2 continuity, Prometheus failure isolation, and Grafana failure isolation. The core metrics snapshot asserts family presence, not exact dynamic counter values.

Performance acceptance compares observability OFF and ON for API P95, Graph P95, Override P95, and Worker throughput. G1 must retain QPS `>=200`, P95 `<300 ms`, and Error Rate `<0.1%`; raw before/after results are recorded without claiming zero overhead.

## 17. Deferred scope

Loki, Tempo, Jaeger, OpenTelemetry Collector/SDK, Alertmanager, email, Slack, enterprise WeChat, PagerDuty, cAdvisor, infrastructure exporter containers, Kubernetes, Redis Sentinel, MySQL HA, Qdrant Cluster, and Neo4j Cluster are deferred production-hardening work.

## 18. Design self-review

- Metric labels use the allowlist and never contain task/thread/entity IDs or free text.
- Browser access to Prometheus is prohibited.
- Grafana and Prometheus are never business dependencies.
- Acceptance baselines remain separate from live metrics.
- Existing `/health`, Monitoring mode isolation, audit, and failure degradation are reused.
- Exactly two services are added.
- Metrics are process singletons and best-effort side effects.
- The design contains no production implementation and changes no business rule.
