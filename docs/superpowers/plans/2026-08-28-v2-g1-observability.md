# CountyFlow V2-G1 Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-safe metrics foundation, Prometheus/Grafana stack, SLO rules, structured correlation, and live Frontend Monitoring without changing CountyFlow business decisions.

**Architecture:** Backend, Worker-1, and Worker-2 expose internal-only Prometheus registries on port 9100. Prometheus and Grafana are provisioned from repository files; browsers read only typed, authorized FastAPI DTOs backed by a fixed PromQL catalog. Metrics are bounded best-effort side effects, while acceptance baselines remain separate non-live evidence.

**Tech Stack:** Python 3.12, FastAPI, prometheus-client, httpx, Redis 8, MySQL, Qdrant, Neo4j, Docker Compose, Prometheus, Grafana, React, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-28-v2-g1-observability-design.md`

## Global Constraints

- Preserve the eight-agent order and all V2-A through V2-F business semantics.
- Add only Prometheus and Grafana; final Compose service count is 11.
- Never put task/thread/entity IDs, free text, raw paths, or raw exceptions in metric labels.
- Browser code never calls Prometheus and API mode never falls back to Monitoring mock data.
- Metrics, Prometheus, and Grafana failures never affect Dispatch, Worker, Agent, Checkpoint, Shared Memory, Graph Memory, or Runtime Override results.
- Live operational metrics and Verified Acceptance Baselines remain visibly and structurally separate.
- Production Observability Read API requires `monitor:read` and fails closed without an external authorizer.
- Keep Prometheus/Worker metrics ports internal; publish only configured Grafana access.
- Use RED → confirm failure → GREEN → REFACTOR → regression for every task.
- Do not modify metric thresholds or label enums without updating `docs/observability_spec.md` and `docs/slo.md` in the same task.

---

### Task 1: Metrics catalog, cardinality contract, and safe recorder

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/observability/__init__.py`
- Create: `backend/app/observability/labels.py`
- Create: `backend/app/observability/catalog.py`
- Create: `backend/app/observability/recorder.py`
- Create: `backend/tests/observability/__init__.py`
- Create: `backend/tests/observability/test_catalog.py`
- Create: `backend/tests/observability/test_recorder.py`

**Interfaces:**
- Produces `METRIC_LABEL_ALLOWLIST: frozenset[str]` and per-family value enums.
- Produces `MetricsRecorder`, `NoOpMetricsRecorder`, `PrometheusMetricsRecorder`, and `SafeMetricsRecorder`.
- Produces `build_metric_catalog(registry: CollectorRegistry) -> MetricCatalog`.
- Later tasks receive only `MetricsRecorder`; they do not import `prometheus_client`.

- [ ] **Step 1: Write failing catalog/cardinality tests**

```python
def test_metric_catalog_uses_only_allowlisted_labels():
    registry = CollectorRegistry()
    catalog = build_metric_catalog(registry)
    assert catalog.family_names() >= {
        "countyflow_http_requests_total",
        "countyflow_agent_executions_total",
        "countyflow_graph_queries_total",
        "countyflow_checkpoint_operations_total",
        "countyflow_runtime_overrides_total",
        "countyflow_worker_messages_total",
    }
    for family in catalog.definitions:
        assert set(family.labels) <= METRIC_LABEL_ALLOWLIST
        assert FORBIDDEN_LABELS.isdisjoint(family.labels)

def test_catalog_rejects_unknown_label_value():
    recorder = PrometheusMetricsRecorder(build_metric_catalog(CollectorRegistry()))
    with pytest.raises(MetricLabelError):
        recorder.observe_agent("unknown-agent", "success", 0.01)
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_catalog.py -q`  
Expected: FAIL because `app.observability` and its catalog do not exist.

- [ ] **Step 3: Add production dependencies and exact contracts**

Add `prometheus-client>=0.21,<1` and move `httpx>=0.28,<1` into production dependencies. Define the exact allowlist from `docs/observability_spec.md`; use frozen definitions rather than accepting arbitrary metric names.

```python
@dataclass(frozen=True)
class MetricDefinition:
    name: str
    kind: Literal["counter", "gauge", "histogram"]
    labels: tuple[str, ...]
    buckets: tuple[float, ...] = ()

class MetricsRecorder(Protocol):
    def observe_http(self, method: str, route_template: str, status_class: str, seconds: float) -> None: ...
    def observe_agent(self, agent: str, result: str, seconds: float) -> None: ...
    def observe_operation(self, subsystem: str, operation: str, result: str, seconds: float | None = None) -> None: ...
    def set_state_count(self, metric: str, result: str, count: int, *, store: str | None = None) -> None: ...
    def increment_invariant(self, reason_code: str, *, store: str | None = None) -> None: ...
```

- [ ] **Step 4: Make recording failure business-safe**

```python
class SafeMetricsRecorder:
    def __init__(self, delegate: MetricsRecorder, logger: logging.Logger) -> None:
        self._delegate = delegate
        self._logger = logger

    def observe_agent(self, agent: str, result: str, seconds: float) -> None:
        try:
            self._delegate.observe_agent(agent, result, seconds)
        except Exception:
            self._logger.debug("metrics_record_failed", extra={"error_code": "METRICS_RECORD_FAILED"})
```

Implement the same guarded forwarding for every protocol method; never catch business exceptions around the operation being measured.

- [ ] **Step 5: Run GREEN and regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_catalog.py backend/tests/observability/test_recorder.py -q`  
Expected: PASS, including duplicate catalog creation with two isolated registries and a throwing delegate that leaves a sentinel business result unchanged.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/pyproject.toml backend/app/observability backend/tests/observability
git commit -m "feat: add bounded observability metrics registry"
```

### Task 2: Settings and internal metrics HTTP lifecycle

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `.docker.env.example`
- Create: `backend/app/observability/server.py`
- Create: `backend/app/observability/runtime.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/worker_entrypoint.py`
- Test: `backend/tests/unit/test_settings.py`
- Create: `backend/tests/observability/test_metrics_server.py`
- Modify: `backend/tests/unit/test_health.py`

**Interfaces:**
- Produces `MetricsRuntime.start()` and `MetricsRuntime.stop()` idempotent lifecycle.
- Settings: `metrics_enabled`, `metrics_host`, `metrics_port`, `observability_sample_interval_seconds`, `observability_probe_timeout_seconds`.
- `build_metrics_runtime(settings, registry=None) -> MetricsRuntime` returns NoOp runtime when disabled.

- [ ] **Step 1: Write failing lifecycle and settings tests**

```python
def test_metrics_runtime_starts_once_and_stops_cleanly(fake_server_factory):
    runtime = MetricsRuntime(fake_server_factory, host="0.0.0.0", port=9100)
    runtime.start()
    runtime.start()
    runtime.stop()
    assert fake_server_factory.start_calls == 1
    assert fake_server_factory.stop_calls == 1

def test_production_rejects_observability_with_multiple_backend_processes_without_multiprocess_dir():
    with pytest.raises(ValueError, match="PROMETHEUS_MULTIPROC_DIR"):
        Settings(runtime_profile="production", metrics_enabled=True, backend_processes=2, prometheus_multiproc_dir="", **safe_production_settings())
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_metrics_server.py backend/tests/unit/test_settings.py -q`  
Expected: FAIL because the lifecycle/settings are absent.

- [ ] **Step 3: Implement internal server and process registry**

Use `prometheus_client.start_http_server(port, addr, registry=registry)` and retain returned server/thread handles. Backend startup and shutdown call the runtime. Worker `run()` starts it before consuming and stops it in `finally`. Do not add `ports:` for 9100 in Compose.

- [ ] **Step 4: Expose only safe capability state in `/health`**

Add `metrics: enabled|disabled` and `observability_api: enabled|disabled` to `runtime_summary()`; never return Prometheus URL, Grafana credentials, or internal endpoints.

- [ ] **Step 5: Run GREEN and full settings regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_metrics_server.py backend/tests/unit/test_settings.py backend/tests/unit/test_health.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/core/config.py backend/app/observability backend/app/main.py backend/app/worker_entrypoint.py backend/tests .env.example .docker.env.example
git commit -m "feat: serve process metrics on internal endpoints"
```

### Task 3: HTTP, application-error, and WebSocket instrumentation

**Files:**
- Create: `backend/app/observability/http.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/v1/task_events.py`
- Create: `backend/tests/observability/test_http_metrics.py`
- Create: `backend/tests/observability/test_websocket_metrics.py`
- Modify: `backend/tests/api/test_task_websocket.py`

**Interfaces:**
- Produces `MetricsMiddleware(app, recorder)`.
- Produces `route_template_from_scope(scope) -> str` returning a registered template or `unmatched`.
- Produces `event_group(TaskEventType) -> Literal[...]`.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_http_metrics_use_route_template(client, registry):
    client.get("/api/v1/dispatch-tasks/TASK-0123456789abcdef0123456789abcde/status")
    text = generate_latest(registry).decode()
    assert 'route_template="/api/v1/dispatch-tasks/{task_id}/status"' in text
    assert "TASK-0123456789abcdef0123456789abcde" not in text

def test_expected_business_409_is_not_an_application_error(client, registry):
    response = client.post("/api/v1/runtime/threads/cf:dispatch:TASK-x/overrides", json=conflict_payload())
    assert response.status_code == 409
    assert "countyflow_application_errors_total" not in generated_samples(registry)
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_http_metrics.py backend/tests/observability/test_websocket_metrics.py -q`  
Expected: FAIL because middleware and WebSocket instrumentation are absent.

- [ ] **Step 3: Implement middleware after-route template lookup**

Increment in-flight before `call_next`, use `request.scope["route"].path` after routing, classify status by hundreds, and observe duration in `finally`. Normalize unmatched/error cases without reading raw URL paths.

- [ ] **Step 4: Instrument WebSocket lifecycle**

Wrap accepted connections in increment/decrement `try/finally`. Map TaskEvent types to `task|agent|memory|thread|override|terminal`; record only `sent|replayed|resync|error`.

- [ ] **Step 5: Run GREEN and API regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_http_metrics.py backend/tests/observability/test_websocket_metrics.py backend/tests/api -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/observability/http.py backend/app/main.py backend/app/api/v1/task_events.py backend/tests
git commit -m "feat: instrument HTTP and WebSocket boundaries"
```

### Task 4: Eight-Agent, Environment, Vector, and Graph metrics

**Files:**
- Modify: `backend/app/graph/dependencies.py`
- Modify: `backend/app/graph/builder.py`
- Modify: `backend/app/runtime.py`
- Modify: `backend/app/services/environment.py`
- Modify: `backend/app/memory/service.py`
- Modify: `backend/app/graph_memory/service.py`
- Modify: `backend/app/agents/graph_memory.py`
- Create: `backend/tests/observability/test_agent_metrics.py`
- Create: `backend/tests/observability/test_memory_metrics.py`
- Modify: `backend/tests/graph/test_ai_core_final.py`

**Interfaces:**
- `GraphDependencies.metrics: MetricsRecorder` defaults to NoOp.
- The existing `_instrument_node(name, node, metrics)` owns agent timing/in-flight/result classification.
- Services receive focused recorder adapters or the NoOp facade through constructors.

- [ ] **Step 1: Write failing Agent/Memory tests**

```python
async def test_eight_known_agents_emit_duration_without_task_label(registry):
    await graph_with_metrics(registry).ainvoke(valid_state())
    text = generate_latest(registry).decode()
    for agent in NODE_ORDER:
        assert f'agent="{agent}"' in text
    assert "task_id=" not in text

async def test_graph_degradation_records_bounded_reason_and_preserves_routing(registry):
    result = await graph_with_failing_neo4j(registry).ainvoke(valid_state())
    assert result["graph_memory_used"] is False
    assert result["decision"] == "REROUTE"
    assert metric_value(registry, "countyflow_graph_memory_degraded_total", reason_code="unavailable") == 1
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_agent_metrics.py backend/tests/observability/test_memory_metrics.py -q`  
Expected: FAIL because no live Agent/Memory metrics exist.

- [ ] **Step 3: Extend the centralized node wrapper**

Measure with `perf_counter()`, increment/decrement in-flight in `try/finally`, re-raise cancellation, and classify patches as `success`, `review_required`, `degraded`, `error`, or `cancelled`. Do not alter node outputs except existing checkpoint metadata.

- [ ] **Step 4: Instrument service results**

Record Environment primary/fallback results and safe reason codes, Vector hit/miss/error, Graph operation/result/duration, and Graph degradation. Preserve all current exceptions and degradation outputs.

- [ ] **Step 5: Run GREEN and graph regressions**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_agent_metrics.py backend/tests/observability/test_memory_metrics.py backend/tests/graph backend/tests/graph_memory backend/tests/memory -q`  
Expected: PASS with unchanged core `memory-rain-li → national-102 → REROUTE → APPROVED` behavior.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/graph backend/app/runtime.py backend/app/services/environment.py backend/app/memory backend/app/graph_memory backend/app/agents/graph_memory.py backend/tests
git commit -m "feat: instrument agents and memory services"
```

### Task 5: Shared Memory, Checkpoint, and Runtime Override metrics

**Files:**
- Modify: `backend/app/shared_memory/service.py`
- Modify: `backend/app/shared_memory/reconciler.py`
- Modify: `backend/app/runtime_threads/checkpoint_store.py`
- Modify: `backend/app/runtime_threads/runner.py`
- Modify: `backend/app/runtime_threads/reconciler.py`
- Modify: `backend/app/runtime_overrides/service.py`
- Modify: `backend/app/runtime_overrides/reconciler.py`
- Create: `backend/tests/observability/test_shared_memory_metrics.py`
- Create: `backend/tests/observability/test_checkpoint_metrics.py`
- Create: `backend/tests/observability/test_override_metrics.py`

**Interfaces:**
- All constructors accept `metrics: MetricsRecorder = NOOP_METRICS`.
- Terminal result recording occurs after authoritative status selection.
- `record_override_downstream_stale()` is called only by the existing invariant comparison boundary.

- [ ] **Step 1: Write failing result/invariant tests**

```python
async def test_partial_mutation_records_partial_without_changing_result(registry):
    result = await partial_service(registry).mutate(command())
    assert result.status is MutationStatus.PARTIAL
    assert metric_value(registry, "countyflow_memory_mutations_total", decision="CREATE", result="PARTIAL") == 1

async def test_metrics_failure_does_not_fail_override():
    result = await override_service(metrics=throwing_recorder()).apply(thread_id, request())
    assert result.status is RuntimeOverrideStatus.APPLIED
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_shared_memory_metrics.py backend/tests/observability/test_checkpoint_metrics.py backend/tests/observability/test_override_metrics.py -q`  
Expected: FAIL because these constructors and families are not wired.

- [ ] **Step 3: Instrument authoritative boundaries**

Use existing domain enums as inputs and map them to catalog values. Observe checkpoint write/read/promote/resume/reconcile duration and payload bytes. Record Override conflicts from normalized codes only; never use reason text, IDs, or actor values.

- [ ] **Step 4: Add downstream safety counter**

At the existing Capacity-after-Override comparison, increment only when APPLIED canonical state differs from the value consumed downstream. Keep the current safe business response unchanged.

- [ ] **Step 5: Run GREEN and subsystem regressions**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_shared_memory_metrics.py backend/tests/observability/test_checkpoint_metrics.py backend/tests/observability/test_override_metrics.py backend/tests/shared_memory backend/tests/runtime_threads backend/tests/runtime_overrides -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/shared_memory backend/app/runtime_threads backend/app/runtime_overrides backend/tests
git commit -m "feat: instrument memory and runtime control planes"
```

### Task 6: Worker, Redis, dependency probes, and current-state gauges

**Files:**
- Modify: `backend/app/workers/dispatch_worker.py`
- Modify: `backend/app/streams/redis_queue.py`
- Create: `backend/app/observability/probes.py`
- Create: `backend/app/observability/sampler.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/runtime.py`
- Create: `backend/tests/observability/test_worker_metrics.py`
- Create: `backend/tests/observability/test_dependency_metrics.py`
- Create: `backend/tests/observability/test_state_sampler.py`
- Modify: `backend/tests/workers/test_pending_recovery.py`

**Interfaces:**
- `DependencyProbeService.run_once() -> tuple[DependencyProbeResult, ...]` probes exactly MySQL/Redis/Qdrant/Neo4j.
- `OperationalStateSampler.run_once()` updates current-state gauges from bounded repository queries.
- `RedisStreamQueue.claim_pending(...)` retains bounded `pending_idle_ms_at_claim` metadata obtained from Redis pending-entry data; it does not add message IDs or idle values as labels.
- Worker recovery duration is `(pending_idle_ms_at_claim / 1000) + claim_to_terminal_ack_seconds`; only the external failure harness measures exact kill `T1` to recovered ACK `T6`.
- Both loops have explicit start/stop and never execute inside a business request/transaction.

- [ ] **Step 1: Write failing Worker/probe tests**

```python
async def test_worker_recovery_slo_counter(registry):
    worker = recovery_worker(
        registry,
        pending_idle_ms_at_claim=4_900,
        claim_to_terminal_ack_seconds=0.101,
    )
    await worker.recover_once()
    assert metric_value(registry, "countyflow_worker_recovery_slo_breaches_total", worker="worker-1") == 1

async def test_dependency_failure_sets_up_zero_without_raising(registry):
    service = dependency_service(registry, neo4j=TimeoutError())
    await service.run_once()
    assert metric_value(registry, "countyflow_dependency_up", dependency="neo4j") == 0
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_worker_metrics.py backend/tests/observability/test_dependency_metrics.py backend/tests/observability/test_state_sampler.py -q`  
Expected: FAIL because probes/sampler and Worker metrics are absent.

- [ ] **Step 3: Instrument Worker and Redis outcomes**

Record the final `WorkerProcessResult`, ACK/retry/recover/DLQ result, fixed Worker name, observable recovery estimate, and breach counter. Read pending idle milliseconds through the bounded Redis pending/claim path, add claim-to-terminal-ACK elapsed time, and never infer or fabricate an external kill timestamp. Redis adapters record bounded operation errors and re-raise/normalize exactly as before.

- [ ] **Step 4: Implement bounded background sampling**

Run every 15 seconds; each dependency probe has an 800 ms timeout. Queries aggregate counts by approved enum and never load individual payloads into labels. A failed sample marks its dependency/probe state unavailable; it does not publish a fabricated zero count.

- [ ] **Step 5: Run GREEN and Worker regressions**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_worker_metrics.py backend/tests/observability/test_dependency_metrics.py backend/tests/observability/test_state_sampler.py backend/tests/workers backend/tests/streams -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/workers backend/app/streams backend/app/observability backend/app/main.py backend/app/runtime.py backend/tests
git commit -m "feat: add worker and dependency operational metrics"
```

### Task 7: Structured logs and end-to-end correlation

**Files:**
- Create: `backend/app/observability/context.py`
- Create: `backend/app/observability/logging.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/streams/models.py`
- Modify: `backend/app/services/dispatch_task_api_service.py`
- Modify: `backend/app/workers/dispatch_worker.py`
- Modify: `backend/app/graph/state.py`
- Modify: `backend/app/events/models.py`
- Modify: `backend/app/audit/service.py`
- Create: `backend/tests/observability/test_correlation.py`
- Create: `backend/tests/observability/test_structured_logging.py`
- Modify: `backend/tests/streams/test_redis_queue.py`
- Modify: `backend/tests/api/test_task_events.py`

**Interfaces:**
- `normalize_correlation_id(value: str | None) -> str` returns/generates a maximum-64-character safe ID.
- `bind_observability_context(...)` returns a context manager/token reset helper.
- `DispatchTaskMessage.correlation_id` and `TaskEvent.correlation_id` are optional and backward-compatible.

- [ ] **Step 1: Write failing propagation and secret-safety tests**

```python
async def test_correlation_crosses_api_message_worker_event_and_audit():
    response = await submit(headers={"X-Request-ID": "ops-123"})
    assert response.headers["X-Request-ID"] == "ops-123"
    assert published_message.correlation_id == "ops-123"
    assert terminal_event.correlation_id == "ops-123"
    assert audit_evidence["correlation_id"] == "ops-123"

def test_json_log_never_serializes_secrets(caplog):
    log_with_context(api_key=SecretStr("forbidden-value"))
    assert "forbidden-value" not in caplog.text
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_correlation.py backend/tests/observability/test_structured_logging.py -q`  
Expected: FAIL because correlation and JSON formatting are absent.

- [ ] **Step 3: Implement context and format selection**

Use `ContextVar` fields and a standard-library JSON formatter. docker-dev/production select JSON; local/test select human-readable unless explicitly overridden. Validate inbound IDs against `[A-Za-z0-9._-]{1,64}` and generate a UUID hex when invalid/missing.

- [ ] **Step 4: Propagate without breaking stored payloads**

Add optional fields with tolerant deserialization. Bind Worker context for the duration of one message and reset in `finally`. Add correlation to graph state, event top-level DTO, and existing audit evidence JSON; do not add a new database or expose credentials.

- [ ] **Step 5: Run GREEN and stream/event/audit regressions**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_correlation.py backend/tests/observability/test_structured_logging.py backend/tests/streams backend/tests/api/test_task_events.py backend/tests/unit/test_audit_service.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/observability backend/app/main.py backend/app/streams backend/app/services/dispatch_task_api_service.py backend/app/workers backend/app/graph/state.py backend/app/events backend/app/audit backend/tests
git commit -m "feat: propagate safe observability correlation"
```

### Task 8: Authorized Observability Read API and fixed PromQL catalog

**Files:**
- Create: `backend/app/observability/auth.py`
- Create: `backend/app/observability/models.py`
- Create: `backend/app/observability/prometheus.py`
- Create: `backend/app/observability/query_catalog.py`
- Create: `backend/app/observability/service.py`
- Create: `backend/app/api/v1/observability_schemas.py`
- Create: `backend/app/api/v1/observability.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/tests/observability/test_query_catalog.py`
- Create: `backend/tests/observability/test_read_service.py`
- Create: `backend/tests/api/test_observability.py`

**Interfaces:**
- `ObservabilityAuthorizer.authorize_read() -> ObservabilityAuthorizationContext` requiring `monitor:read`.
- `PrometheusQueryClient.instant(query_key, params)` and `.range(query_key, window)` accept enum keys, never raw PromQL.
- `ObservabilityReadService` produces typed `LIVE|STALE|UNAVAILABLE` domain DTOs.

- [ ] **Step 1: Write failing API/auth/query tests**

```python
def test_prometheus_query_allowlist_rejects_raw_promql():
    with pytest.raises(UnknownObservabilityQuery):
        catalog.resolve('rate(secret_metric[5m])')

def test_observability_api_requires_permission(client):
    assert client.get("/api/v1/observability/summary?window=5m").status_code == 403

def test_prometheus_unavailable_returns_safe_503(client):
    response = client.get("/api/v1/observability/summary?window=5m")
    assert response.status_code == 503
    assert response.json()["code"] == "OBSERVABILITY_UNAVAILABLE"
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_query_catalog.py backend/tests/observability/test_read_service.py backend/tests/api/test_observability.py -q`  
Expected: FAIL because the read boundary does not exist.

- [ ] **Step 3: Implement six typed endpoints**

Mount summary/agents/workers/memory/runtime/dependencies only when enabled. Accept `window` as an enum `5m|15m|1h`. Return nullable values and safe timestamps; never return raw Prometheus JSON, PromQL, internal credentials, or series identifiers.

- [ ] **Step 4: Implement LIVE/STALE/UNAVAILABLE**

Use one-second HTTP timeout. Freshest required samples `<=45s` are LIVE, `45–120s` or bounded partial sets are STALE, and request/shape errors or age `>120s` produce safe 503. Authorization failure is 403 and never contacts Prometheus.

- [ ] **Step 5: Run GREEN and API regression**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability backend/tests/api -q`  
Expected: PASS.

- [ ] **Step 6: Commit implementation slice**

```powershell
git add backend/app/observability backend/app/api/v1/observability.py backend/app/api/v1/observability_schemas.py backend/app/main.py backend/app/core/config.py backend/tests
git commit -m "feat: add authorized observability read API"
```

### Task 9: Prometheus, rules, Grafana provisioning, and 11-service Compose

**Files:**
- Create: `monitoring/prometheus/prometheus.yml`
- Create: `monitoring/prometheus/rules/recording.yml`
- Create: `monitoring/prometheus/rules/alerts.yml`
- Create: `monitoring/grafana/provisioning/datasources/prometheus.yml`
- Create: `monitoring/grafana/provisioning/dashboards/dashboard.yml`
- Create: `monitoring/grafana/dashboards/countyflow-v2-operations.json`
- Modify: `docker-compose.yml`
- Modify: `.docker.env.example`
- Modify: `.gitignore`
- Modify: `.dockerignore`
- Modify: `scripts/start-full.ps1`
- Modify: `backend/tests/unit/test_docker_runtime_files.py`
- Create: `backend/tests/observability/test_monitoring_config.py`

**Interfaces:**
- Prometheus job names are exactly `backend`, `worker-1`, `worker-2`.
- Prometheus retention is 7d; scrape interval 15s; timeout 5s.
- Grafana datasource UID is `countyflow-prometheus`; dashboard UID is `countyflow-v2-operations`.

- [ ] **Step 1: Write failing static configuration tests**

```python
def test_compose_declares_exactly_eleven_services_and_internal_metric_targets():
    compose = load_compose()
    assert len(compose["services"]) == 11
    assert {"prometheus", "grafana"} <= compose["services"].keys()
    for service in ("backend", "worker-1", "worker-2"):
        assert "9100:9100" not in compose["services"][service].get("ports", [])

def test_dashboard_and_rules_are_provisioned_without_manual_steps():
    assert dashboard_uid() == "countyflow-v2-operations"
    assert datasource_uid() == "countyflow-prometheus"
    assert required_alert_names() <= loaded_alert_names()
```

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_monitoring_config.py backend/tests/unit/test_docker_runtime_files.py -q`  
Expected: FAIL because monitoring files and services do not exist.

- [ ] **Step 3: Add Prometheus and rule files**

Use file-mounted configuration, three application scrape jobs, recording expressions from `docs/observability_spec.md`, and alerts from `docs/slo.md`. Run `promtool check config` and `promtool check rules` through the pinned Prometheus image.

- [ ] **Step 4: Add Grafana provisioning and dashboard JSON**

Provision datasource URL `http://prometheus:9090`; create the nine approved sections. Do not embed acceptance fixtures in Grafana JSON. Credentials use `${GRAFANA_ADMIN_USER}` and `${GRAFANA_ADMIN_PASSWORD}` with required nonempty `.docker.env` values and no committed default password.

- [ ] **Step 5: Expand Compose and launcher**

Add named volumes `countyflow_prometheus` and `countyflow_grafana`, healthchecks, Grafana host mapping from `${GRAFANA_PORT:-3000}`, internal Prometheus, and dependencies that do not make Backend/Worker wait on monitoring services. The business stack must start when either monitoring service is unavailable.

- [ ] **Step 6: Run GREEN**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/observability/test_monitoring_config.py backend/tests/unit/test_docker_runtime_files.py -q`  
Run: `docker compose --env-file .docker.env config --quiet`  
Expected: both PASS and exactly 11 declared services.

- [ ] **Step 7: Commit implementation slice**

```powershell
git add monitoring docker-compose.yml .docker.env.example .gitignore .dockerignore scripts/start-full.ps1 backend/tests
git commit -m "feat: provision Prometheus and Grafana"
```

### Task 10: Frontend Live Monitoring without Mock fallback

**Files:**
- Create: `frontend/src/types/observability.ts`
- Create: `frontend/src/services/api/observability-client.ts`
- Create: `frontend/src/hooks/use-observability.ts`
- Create: `frontend/src/components/live-observability-panel.tsx`
- Create: `frontend/src/components/observability-trend.tsx`
- Modify: `frontend/src/pages/monitor-page.tsx`
- Modify: `frontend/src/config/runtime.ts`
- Modify: `frontend/src/styles/index.css`
- Create: `frontend/tests/observability-client.test.ts`
- Create: `frontend/tests/monitoring-live.test.tsx`
- Modify: `frontend/tests/v2-product-surfaces.test.tsx`

**Interfaces:**
- `getObservabilitySummary(window, signal) -> Promise<ObservabilitySummary>` calls only FastAPI.
- `useObservability(window)` returns `{state,data,error,refresh}` with `LIVE|STALE|UNAVAILABLE|NO_PERMISSION`.
- `ObservabilityWindow` is `"5m" | "15m" | "1h"`.

- [ ] **Step 1: Write failing frontend contract tests**

```tsx
it("keeps live and verified baseline sections separate", async () => {
  render(<MonitorPage />);
  expect(await screen.findByText("LIVE OBSERVABILITY")).toBeVisible();
  expect(screen.getByText("VERIFIED ACCEPTANCE BASELINE")).toBeVisible();
});

it("does not use monitoring mock after API failure", async () => {
  server.use(observability503());
  render(<MonitorPage />);
  expect(await screen.findByText("Monitoring unavailable")).toBeVisible();
  expect(screen.queryByText("DEMO DATA")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run from `frontend`: `npm test -- --run tests/observability-client.test.ts tests/monitoring-live.test.tsx`  
Expected: FAIL because the client/hook/panels do not exist.

- [ ] **Step 3: Implement typed client and state hook**

Map 403 to NO_PERMISSION and safe 503 to UNAVAILABLE. Abort stale requests when the time range changes. Do not import files under `src/mocks` from the API-mode hook or client.

- [ ] **Step 4: Extend the current Monitoring page**

Add Current QPS, API P95, Error Rate, Agent P95, Worker Pending/Lag, Graph P95, Checkpoint P95, Override results, Memory PARTIAL, and Dependencies. Render missing values as `—`, never zero. Use small existing-style SVG trends; preserve `VerifiedBaselinePanel` unchanged.

- [ ] **Step 5: Add safe Grafana link and responsive states**

Render `Open Grafana` only from the safe API DTO. Support 5m/15m/1h, LIVE/STALE/UNAVAILABLE/NO_PERMISSION, keyboard operation, reduced motion, 1366/1440/1920 layouts, and no horizontal overflow.

- [ ] **Step 6: Run GREEN and frontend regression**

Run from `frontend`: `npm test -- --run tests/observability-client.test.ts tests/monitoring-live.test.tsx tests/v2-product-surfaces.test.tsx`  
Run from `frontend`: `npm run lint`  
Run from `frontend`: `npm run build`  
Expected: PASS with 0 lint warnings.

- [ ] **Step 7: Commit implementation slice**

```powershell
git add frontend/src frontend/tests
git commit -m "feat: add live observability monitoring UI"
```

### Task 11: Real Docker targets, provisioning, browser failures, and overhead acceptance

**Files:**
- Create: `scripts/test-observability.ps1`
- Create: `scripts/observability_integration.py`
- Create: `scripts/observability_failure_e2e.py`
- Create: `scripts/observability_overhead.py`
- Create: `frontend/e2e/observability-live.spec.ts`
- Create: `frontend/e2e/observability-failures.spec.ts`
- Modify: `scripts/test-docker.ps1`
- Modify: `scripts/check.ps1`
- Create: `docs/verification/v2-g1/observability-acceptance.md`
- Create during verified runs: `docs/verification/v2-g1/raw/prometheus-targets.json`
- Create during verified runs: `docs/verification/v2-g1/raw/grafana-provisioning.json`
- Create during verified runs: `docs/verification/v2-g1/raw/browser-e2e.json`
- Create during verified runs: `docs/verification/v2-g1/raw/failure-e2e.json`
- Create during verified runs: `docs/verification/v2-g1/raw/overhead.json`

**Interfaces:**
- Integration scripts return nonzero on any missing target/dashboard/failure-isolation invariant.
- Raw JSON contains no credentials, headers, raw Prometheus payloads, or high-cardinality identifiers beyond bounded test task references already allowed in verification evidence.

- [ ] **Step 1: Write failing harness contract tests**

Add tests to `backend/tests/unit/test_docker_runtime_files.py` proving scripts require all three targets, provisioned datasource/dashboard, API-mode browser, Neo4j/Worker/Prometheus/Grafana failure cases, and before/after overhead fields.

- [ ] **Step 2: Run RED**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/unit/test_docker_runtime_files.py -q`  
Expected: FAIL because the G1 harnesses are absent.

- [ ] **Step 3: Implement real target and snapshot acceptance**

Verify Prometheus target health for `backend`, `worker-1`, `worker-2`; run one real dispatch; scrape application families and assert HTTP, eight-Agent, Vector, Graph, Checkpoint, Override, and Worker family presence without exact dynamic values. Verify Grafana datasource/dashboard through its health and search APIs using credentials loaded from ignored environment without printing them.

- [ ] **Step 4: Implement failure E2E**

1. Stop Neo4j, await `dependency_up{dependency="neo4j"}=0`, prove Graph degradation and business continuation, restart, await 1.
2. Stop Worker-1, prove its target down and Worker-2 up, submit a task, prove recovery, restart.
3. Stop Prometheus, prove frontend/API UNAVAILABLE and business submission succeeds, restart, await LIVE.
4. Stop Grafana, prove business and internal Monitoring still work, restart, await health.

Always restore services in `finally`; never remove named volumes.

- [ ] **Step 5: Implement observability OFF versus ON benchmark**

Run the locked workload twice with the same dataset and concurrency. Record API P95, Graph P95, Override P95, Worker throughput, QPS, and error rate. PASS requires ON QPS `>=200`, P95 `<300 ms`, Error Rate `<0.1%`; report percentage deltas without inventing a zero-overhead target.

- [ ] **Step 6: Run real acceptance and browser E2E**

Run: `powershell -ExecutionPolicy Bypass -File scripts/test-observability.ps1`  
Run from `frontend`: `npx playwright test e2e/observability-live.spec.ts e2e/observability-failures.spec.ts`  
Expected: all targets/provisioning/failure cases PASS; browser console/page errors 0.

- [ ] **Step 7: Run full regression gates**

Run: `.venv\Scripts\python.exe -m ruff check backend`  
Run: `.venv\Scripts\python.exe -m pytest`  
Run from `frontend`: `npm run lint`  
Run from `frontend`: `npm test -- --run`  
Run from `frontend`: `npm run build`  
Run: `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`  
Run: `docker compose --env-file .docker.env config --quiet`  
Run: `git diff --check`  
Run: `git diff --cached --check`  
Expected: all PASS, Compose 11 services, migration Exited(0), Redis Pending 0, secret scan 0.

- [ ] **Step 8: Commit verified evidence and harnesses**

```powershell
git add scripts frontend/e2e docs/verification/v2-g1
git commit -m "test: verify production observability stack"
```

## Required named test coverage

The implementation may split assertions across focused files, but the following behavior names are mandatory and remain traceable to the requested acceptance contract:

| Required test | Primary task / file |
|---|---|
| `test_http_metrics_recorded` | Task 3 / `test_http_metrics.py` |
| `test_http_metrics_use_route_template` | Task 3 / `test_http_metrics.py` |
| `test_http_metrics_no_task_id_label` | Task 1 / `test_catalog.py` |
| `test_agent_metrics_known_labels` | Task 4 / `test_agent_metrics.py` |
| `test_agent_duration_histogram` | Task 4 / `test_agent_metrics.py` |
| `test_graph_metrics` | Task 4 / `test_memory_metrics.py` |
| `test_vector_metrics` | Task 4 / `test_memory_metrics.py` |
| `test_memory_mutation_metrics` | Task 5 / `test_shared_memory_metrics.py` |
| `test_projection_metrics` | Task 5 / `test_shared_memory_metrics.py` |
| `test_checkpoint_metrics` | Task 5 / `test_checkpoint_metrics.py` |
| `test_runtime_override_metrics` | Task 5 / `test_override_metrics.py` |
| `test_worker_metrics` | Task 6 / `test_worker_metrics.py` |
| `test_worker_recovery_slo_counter` | Task 6 / `test_worker_metrics.py` |
| `test_dependency_metrics` | Task 6 / `test_dependency_metrics.py` |
| `test_metrics_failure_does_not_fail_business` | Task 1 / `test_recorder.py` |
| `test_metrics_registry_not_double_registered` | Task 1 / `test_catalog.py` |
| `test_observability_summary_api` | Task 8 / `test_observability_api.py` |
| `test_observability_api_requires_permission` | Task 8 / `test_observability_api.py` |
| `test_observability_unavailable_safe` | Task 8 / `test_observability_api.py` |
| `test_prometheus_query_allowlist` | Task 8 / `test_prometheus_query_service.py` |
| `test_frontend_live_metrics` | Task 10 / `monitoring-live.test.tsx` |
| `test_frontend_verified_baseline_separate` | Task 10 / `monitoring-live.test.tsx` |
| `test_frontend_observability_unavailable` | Task 10 / `monitoring-live.test.tsx` |
| `test_frontend_api_mode_no_monitoring_mock` | Task 10 / `monitoring-live.test.tsx` |

Cardinality-contract tests additionally snapshot every metric family and label tuple and fail when a forbidden label, unbounded enum value, or raw route appears.

## Final implementation acceptance

V2-G1 implementation is complete only when all required metric families use bounded labels, repeated app/runtime construction does not duplicate registration, the three real Prometheus targets are UP, Grafana provisioning is automatic, Frontend API mode shows live/stale/unavailable/permission states without Mock fallback, all four failure E2E cases preserve business availability, the ON workload retains approved performance redlines, the full V2 regression remains green, and raw evidence is secret-free and traceable.
