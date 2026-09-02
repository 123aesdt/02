# CountyFlow Observability Specification

**Version:** V2-G1 design  
**Signal priority:** Metrics first; structured-log correlation second; tracing backend deferred.

## 1. Naming and registration rules

- Names use `countyflow_<subsystem>_<metric>`.
- Counters end in `_total`; duration histograms end in `_seconds`; byte histograms end in `_bytes`; gauges do not end in `_total`.
- Metric objects are registered once per process in a dedicated `CollectorRegistry`.
- Application metrics endpoints are `backend:9100/metrics`, `worker-1:9100/metrics`, and `worker-2:9100/metrics`, internal-only.
- Metric recording is best effort and cannot change a business result, exception, transaction, checkpoint, message ACK, or retry decision.
- Acceptance results are not registered as live metrics.

## 2. Label allowlist

Only these application label names are valid:

```text
method
route_template
status_class
agent
result
decision
operation
dependency
worker
event_type
runtime_profile
projection
store
reason_code
```

Forbidden label names include all task, thread, order, dispatch, memory, mutation, override, checkpoint, driver, vehicle, route, user, and operator identifiers, plus `error_message`, free-form `reason`, provider URLs, and raw HTTP paths.

Prometheus-generated target labels such as `job` and `instance` are scrape metadata, not application-controlled labels. Dashboards group Worker series by stable `job` values rather than dynamic consumer IDs.

## 3. Bounded label values

| Label | Allowed values |
|---|---|
| `method` | `GET`, `POST`, `OPTIONS`, `OTHER` |
| `route_template` | Registered FastAPI templates plus `unmatched`; never a concrete URL |
| `status_class` | `2xx`, `3xx`, `4xx`, `5xx` |
| `agent` | `intake`, `entity_memory`, `graph_memory`, `environment`, `capacity`, `routing`, `dispatch`, `audit` |
| `result` | Per-family enum declared below; no arbitrary text |
| `decision` | `CREATE`, `MERGE`, `REPLACE`, `REJECT`, `CONFLICT_REVIEW`, `NOOP` |
| `operation` | Per-family enum declared below |
| `dependency` | `mysql`, `redis`, `qdrant`, `neo4j` |
| `worker` | `worker-1`, `worker-2` |
| `event_type` | `task`, `agent`, `memory`, `thread`, `override`, `terminal` |
| `runtime_profile` | `local`, `test`, `docker-dev`, `production` |
| `projection` | `STAGED`, `FINALIZING`, `ACTIVE`, `RETIRED` |
| `store` | `qdrant`, `neo4j` |
| `reason_code` | Family-specific enum; never raw exception text |

## 4. Metric catalog

### API and WebSocket

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_http_requests_total` | Counter | `method,route_template,status_class` | Completed HTTP requests | FastAPI middleware | API QPS/error | API error |
| `countyflow_http_request_duration_seconds` | Histogram | `method,route_template` | HTTP duration using matched route template | FastAPI middleware | API P50/P95/P99 | API latency |
| `countyflow_http_inflight_requests` | Gauge | none | Requests currently executing | FastAPI middleware | API saturation | Diagnostic |
| `countyflow_application_errors_total` | Counter | `operation,reason_code` | Unexpected normalized application failures; expected 409/422 responses are excluded | Exception boundary | Error breakdown | API error |
| `countyflow_websocket_connections` | Gauge | none | Active task WebSockets | WebSocket lifecycle | Connections | Diagnostic |
| `countyflow_websocket_events_total` | Counter | `event_type,result` | Bounded event groups with `sent`, `replayed`, `resync`, or `error` | Event delivery | Event delivery | Diagnostic |

HTTP histogram buckets in seconds: `0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5`.

### Eight-Agent workflow

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_agent_executions_total` | Counter | `agent,result` | Agent terminal outcomes: `success`, `review_required`, `degraded`, `error`, `cancelled` | Graph node wrapper | Agent outcomes | Diagnostic |
| `countyflow_agent_duration_seconds` | Histogram | `agent` | Agent execution duration | Graph node wrapper | Per-agent P95 | Agent bottleneck |
| `countyflow_agent_inflight` | Gauge | `agent` | Active agent executions | Graph node wrapper | Agent saturation | Diagnostic |

Agent buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.3, 0.5, 1, 2.5`.

### Environment and fallback

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_environment_requests_total` | Counter | `operation,result` | `operation=primary|fallback`; result is `success|error` | Environment service | Provider outcomes | Diagnostic |
| `countyflow_environment_duration_seconds` | Histogram | `operation` | Environment/fallback duration | Environment service | Environment latency | Diagnostic |
| `countyflow_environment_fallback_total` | Counter | `reason_code` | Fallback reasons `timeout`, `http_error`, `circuit_open`, `invalid_response` | Environment service | Fallback rate | Diagnostic |

Environment buckets: `0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1, 2.5`.

### Vector and Graph Memory

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_vector_recall_total` | Counter | `result` | `hit`, `miss`, or `error` | Entity Memory service | Vector activity | Diagnostic |
| `countyflow_vector_recall_duration_seconds` | Histogram | none | Qdrant recall duration | Entity Memory service | Vector P95 | Diagnostic |
| `countyflow_graph_queries_total` | Counter | `operation,result` | `operation=entity|relation|path|multi_hop`; result `success|empty|error` | Graph repository/service | Graph activity | Graph failure |
| `countyflow_graph_query_duration_seconds` | Histogram | `operation` | Bounded Neo4j query duration | Graph repository/service | Graph P95 | Graph latency |
| `countyflow_graph_memory_degraded_total` | Counter | `reason_code` | `unavailable`, `timeout`, `query_error`, `invalid_result` | Graph Memory Agent | Degradation | Graph failure |

Vector/Graph buckets: `0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1`.

Top-1, Top-3, and exact Graph Recall quality remain Verified Acceptance Baselines and never appear in these live families.

### Shared Memory Control Plane

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_memory_mutations_total` | Counter | `decision,result` | Canonical mutation decision and terminal result | Mutation service | Decision matrix | Partial/conflict |
| `countyflow_memory_projection_state` | Gauge | `store,projection` | Current projection count by store/lifecycle; no fact label | Operational state sampler | Projection lifecycle | Partial/stuck |
| `countyflow_memory_partial_mutations` | Gauge | none | Current unresolved PARTIAL count | Operational state sampler | Partial count | Partial stuck |
| `countyflow_memory_reconciliations_total` | Counter | `result` | `success`, `conflict`, `failed`, `noop` | Memory reconciler | Reconciliation | Diagnostic |
| `countyflow_memory_projection_leaks_total` | Counter | `store` | Detected visibility invariant violations | Projection boundary | Invariants | Critical invariant |

Mutation results are `APPLIED`, `PARTIAL`, `CONFLICT`, `FAILED`, `REJECTED`. Projection counts use the approved `projection` enum; internal `PENDING`, `NOT_REQUIRED`, and `FAILED` states are represented by mutation/partial metrics rather than widening the public projection label.

### Runtime Threads and Checkpoints

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_runtime_threads` | Gauge | `result` | Current thread counts: `RUNNING`, `STABLE`, `OVERRIDING`, `TERMINAL` | Operational state sampler | Runtime states | Diagnostic |
| `countyflow_checkpoint_operations_total` | Counter | `operation,result` | Operation `write`, `read`, `promote`, `resume`, `reconcile`; result `success`, `error`, `conflict` | Checkpoint/store/runtime boundaries | Checkpoint operations | Error trend |
| `countyflow_checkpoint_duration_seconds` | Histogram | `operation` | Checkpoint operation duration | Same boundary | Checkpoint P95 | Latency warning |
| `countyflow_checkpoint_payload_bytes` | Histogram | none | Serialized checkpoint payload size | Checkpoint store | State growth | Size diagnostic |
| `countyflow_checkpoint_orphans` | Gauge | none | Current noncanonical orphan count | Operational state sampler | Orphans | Reconciliation |
| `countyflow_checkpoint_reconciliation_total` | Counter | `result` | `success`, `conflict`, `failed`, `noop` | Thread reconciler | Reconciliation | Diagnostic |

Checkpoint duration buckets: `0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1`. Payload buckets in bytes: `1024, 4096, 16384, 65536, 262144, 524288, 1048576`.

### Runtime Override

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_runtime_overrides_total` | Counter | `result` | `APPLIED`, `REJECTED`, `CONFLICT`, `PARTIAL`, `FAILED` | Override service terminal boundary | Override outcomes | Conflict spike |
| `countyflow_runtime_override_duration_seconds` | Histogram | none | End-to-end override duration | Override service | Override P95 | Diagnostic |
| `countyflow_runtime_override_conflicts_total` | Counter | `reason_code` | `version`, `busy`, `not_stable`, `precondition`, `terminal`, `permission` | Override service | Conflict reasons | Conflict spike |
| `countyflow_runtime_override_downstream_stale_total` | Counter | none | APPLIED override followed by old downstream value | Capacity invariant boundary | Invariants | Critical invariant |

Override buckets: `0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5`.

### Workers, Streams, Redis, and DLQ

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_worker_messages_total` | Counter | `worker,result` | `processed`, `acked`, `retried`, `recovered`, `dlq`, `failed` | DispatchWorker | Worker throughput | Diagnostic |
| `countyflow_worker_pending_messages` | Gauge | `worker` | Pending entries attributable to each fixed consumer | Redis summary sampler | Pending | Backlog |
| `countyflow_worker_stream_lag` | Gauge | none | Stream produced-minus-delivered lag | Redis summary sampler | Lag | Lag high |
| `countyflow_worker_recovery_duration_seconds` | Histogram | `worker` | Observable recovery estimate: pending idle at claim plus claim-to-terminal-ACK duration | Recovery path | Recovery P95/max | SLO breach |
| `countyflow_worker_recovery_slo_breaches_total` | Counter | `worker` | Observable recovery estimates greater than 5 seconds | Recovery path | Breaches | Required alert |
| `countyflow_worker_dlq_total` | Counter | `worker` | Messages moved to DLQ | DispatchWorker | DLQ ingress | Diagnostic |
| `countyflow_worker_dlq_messages` | Gauge | none | Current DLQ backlog | Redis summary sampler | DLQ backlog | Diagnostic |
| `countyflow_redis_operation_errors_total` | Counter | `operation` | `stream_read`, `stream_ack`, `lock`, `event`, `checkpoint` | Redis adapters | Redis errors | Dependency/error |

Recovery buckets: `0.25, 0.5, 1, 2, 3, 4, 5, 7.5, 10`.

Prometheus target `up{job="worker-1"}` and `up{job="worker-2"}` is the authoritative process availability signal; no duplicate application `worker_up` gauge is introduced.

### Dependency probes

| Metric | Type | Labels | Description | Source | Dashboard | Alert |
|---|---|---|---|---|---|---|
| `countyflow_dependency_up` | Gauge | `dependency` | Latest bounded probe result, 1 or 0 | Backend dependency sampler | Dependency health | Dependency down |
| `countyflow_dependency_probe_duration_seconds` | Histogram | `dependency` | Probe duration | Backend dependency sampler | Probe latency | Diagnostic |

Probe buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1`.

Redis message loss is not emitted as a live metric because the current runtime cannot prove non-delivery in real time without a new durable sequence protocol. The verified `0` result remains acceptance evidence; creating a misleading live zero gauge is prohibited.

## 5. Recording rules

```promql
# Request volume per second.
countyflow:slo:http_qps_5m =
  sum(rate(countyflow_http_requests_total[5m]))

# P95 API duration.
countyflow:slo:http_p95_5m =
  histogram_quantile(0.95,
    sum by (le) (rate(countyflow_http_request_duration_seconds_bucket[5m])))

# Unexpected server error ratio. Expected 4xx business responses are excluded.
countyflow:slo:http_error_ratio_5m =
  sum(rate(countyflow_http_requests_total{status_class="5xx"}[5m]))
  / clamp_min(sum(rate(countyflow_http_requests_total[5m])), 0.000001)

countyflow:slo:agent_p95_5m =
  histogram_quantile(0.95,
    sum by (agent, le) (rate(countyflow_agent_duration_seconds_bucket[5m])))

countyflow:slo:graph_p95_5m =
  histogram_quantile(0.95,
    sum by (le) (rate(countyflow_graph_query_duration_seconds_bucket[5m])))

countyflow:slo:checkpoint_p95_5m =
  histogram_quantile(0.95,
    sum by (operation, le) (rate(countyflow_checkpoint_duration_seconds_bucket[5m])))

countyflow:slo:override_success_ratio_15m =
  sum(increase(countyflow_runtime_overrides_total{result="APPLIED"}[15m]))
  / clamp_min(sum(increase(countyflow_runtime_overrides_total[15m])), 1)

countyflow:slo:worker_pending = max(countyflow_worker_pending_messages)
countyflow:slo:worker_stream_lag = max(countyflow_worker_stream_lag)
```

## 6. Acceptance baseline boundary

The following are never synthesized into Prometheus live series:

- Vector Top-1 `49/50 = 98%`
- Vector Top-3 `50/50 = 100%`
- Graph Recall `20/20`
- Graph acceptance P95 `10.354 ms`
- 15-round `15/15`
- Runtime Override `50/50`
- Checkpoint Resume `5/5`
- Worker Recovery max `4.824 s`
- Locust minimum QPS `400.071`, maximum P95 `200 ms`, error rate `0%`

They remain immutable, timestamped `VERIFIED ACCEPTANCE BASELINE` data in the product frontend and verification documents.
