# CountyFlow Operational SLO and Alert Specification

**Version:** V2-G1 design  
**Evaluation source:** Prometheus recording and alert rules  
**Notification delivery:** Deferred; G1 evaluates and visualizes rules without Alertmanager.

## 1. Operational SLO versus acceptance evidence

An **Operational SLO** is evaluated repeatedly over a declared Prometheus window from live traffic. An **Acceptance Baseline** is an immutable result from a controlled benchmark or failure exercise. A baseline can justify a threshold, but it is not a live sample and must not be copied into a Prometheus gauge.

| Objective | Live operational definition | Window / guard | Approved boundary |
|---|---|---|---|
| API latency | P95 of matched HTTP route durations | Rolling 5m; at least 100 requests | `<300 ms` |
| API errors | HTTP 5xx ratio; expected 409/422 excluded | Rolling 5m; at least 100 requests | `<0.1%` |
| Graph query latency | P95 bounded Graph query duration | Rolling 5m; at least 20 queries | `<150 ms` |
| Worker recovery | Pending idle at recovery claim plus claim-to-terminal-ACK duration | Counter records each observable estimate above the boundary | `<=5 s` |
| Projection visibility | Detected leak events | Any event | `0` |
| Override downstream safety | Detected stale downstream reads after APPLIED | Any event | `0` |

There is no new availability contract, no 99.9/99.99 target, and no live Top-1/Top-3 or exact-recall SLO in G1.

The live Worker recovery duration is deliberately an operational estimate because the surviving process cannot observe the exact external kill timestamp. The Redis recovery adapter reads each claimed entry's bounded pending idle duration immediately before/with `XAUTOCLAIM`, then adds claim-to-terminal-ACK elapsed time. The formal failure acceptance remains the externally timestamped kill `T1` to recovered durable ACK `T6`; the live estimate does not replace or relabel that black-box evidence.

Checkpoint latency, Worker backlog/lag, partial mutations, and Override conflict ratio are operational warning guardrails, not contractual SLOs. Their initial thresholds are conservative defaults and must be reported separately from SLO compliance.

## 2. Required recording rules

The canonical expressions are defined in `docs/observability_spec.md` and provisioned as `monitoring/prometheus/rules/recording.yml`:

- `countyflow:slo:http_qps_5m`
- `countyflow:slo:http_p95_5m`
- `countyflow:slo:http_error_ratio_5m`
- `countyflow:slo:agent_p95_5m`
- `countyflow:slo:graph_p95_5m`
- `countyflow:slo:checkpoint_p95_5m`
- `countyflow:slo:override_success_ratio_15m`
- `countyflow:slo:worker_pending`
- `countyflow:slo:worker_stream_lag`

## 3. Alert rules

### Availability and dependencies

| Alert | Expression | `for` | Severity | Meaning |
|---|---|---:|---|---|
| `CountyFlowBackendDown` | `up{job="backend"} == 0` | 2m | critical | Backend metrics target is continuously unreachable |
| `CountyFlowWorkerDown` | `up{job=~"worker-1|worker-2"} == 0` | 2m | warning | One fixed Worker process is unavailable; alert retains `job`/`instance` target labels |
| `CountyFlowDependencyDown` | `countyflow_dependency_up == 0` | 2m | warning | A bounded application probe continuously fails |

Grafana displays both Worker targets so an operator can distinguish one-worker degradation from both-worker loss. Notification routing and compound escalation are deferred with Alertmanager.

### Approved SLO alerts

| Alert | Expression | `for` | Severity | Guard |
|---|---|---:|---|---|
| `CountyFlowApiLatencyHigh` | `countyflow:slo:http_p95_5m >= 0.3 and sum(increase(countyflow_http_requests_total[5m])) >= 100` | 10m | warning | Avoid low-volume percentile noise |
| `CountyFlowApiErrorRateHigh` | `countyflow:slo:http_error_ratio_5m >= 0.001 and sum(increase(countyflow_http_requests_total[5m])) >= 100` | 10m | critical | Counts only 5xx; expected 4xx is excluded |
| `CountyFlowGraphLatencyHigh` | `countyflow:slo:graph_p95_5m >= 0.15 and sum(increase(countyflow_graph_queries_total[5m])) >= 20` | 10m | warning | Requires meaningful Graph traffic |
| `CountyFlowWorkerRecoverySloBreach` | `sum(increase(countyflow_worker_recovery_slo_breaches_total[15m])) > 0` | 0m | critical | Counter over the observable pending-idle-plus-claim-to-ACK estimate; never a sticky last-duration gauge |
| `CountyFlowInvariantViolation` | `sum(increase(countyflow_memory_projection_leaks_total[5m])) + increase(countyflow_runtime_override_downstream_stale_total[5m]) > 0` | 0m | critical | Normal objective is always zero |

### Operational warning guardrails

| Alert | Expression | `for` | Severity | Rationale |
|---|---|---:|---|---|
| `CountyFlowWorkerPendingBacklog` | `countyflow:slo:worker_pending > 10` | 10m | warning | Ignores transient pending entries |
| `CountyFlowWorkerStreamLagHigh` | `countyflow:slo:worker_stream_lag > 100` | 10m | warning | Detects sustained producer/consumer imbalance |
| `CountyFlowCheckpointLatencyHigh` | `max(countyflow:slo:checkpoint_p95_5m) > 0.5 and sum(increase(countyflow_checkpoint_operations_total[5m])) >= 20` | 10m | warning | Early-warning threshold, not an approved SLO |
| `CountyFlowMemoryPartialStuck` | `countyflow_memory_partial_mutations > 0` | 10m | warning | Allows bounded reconciliation time |
| `CountyFlowOverrideConflictSpike` | `sum(increase(countyflow_runtime_overrides_total{result="CONFLICT"}[15m])) / clamp_min(sum(increase(countyflow_runtime_overrides_total[15m])), 1) > 0.2 and sum(increase(countyflow_runtime_overrides_total[15m])) >= 10` | 5m | warning | Requires at least ten operations |

Redis Message Loss remains an acceptance invariant because the current runtime has no reliable online detector. G1 does not publish a permanent zero gauge or an alert that cannot observe the failure.

## 4. Dashboard SLO presentation

The Grafana first row shows live API P95, 5xx error ratio, QPS, Worker pending, stream lag, Graph P95, Checkpoint P95, Override applied ratio, partial mutations, and dependency count. Panels display query window and target; warning guardrails are labeled `Operational Guardrail`, not `SLO`.

CountyFlow Frontend Monitoring shows the same small set through typed read DTOs. The separate Verified Baseline panel continues to show:

- Top-1 `49/50 (98%)`, Top-3 `50/50`
- Graph Recall `20/20`, acceptance P95 `10.354 ms`
- 15-round `15/15`
- Override `50/50`, stale `0/50`
- Checkpoint Resume `5/5`
- Worker Recovery max `4.824 s`
- Locust min QPS `400.071`, max P95 `200 ms`, Error Rate `0%`

Those values are never used in live PromQL.

## 5. Failure and missing-data semantics

- No traffic is `NO DATA`, not a zero latency or perfect error ratio.
- A single low-volume 5xx cannot fire the rate alert because the minimum request guard fails.
- A down Prometheus produces `UNAVAILABLE` in the product read API; it does not mark every dependency down.
- Stale samples are explicitly `STALE`; they are not silently treated as current.
- Grafana failure does not affect rule evaluation in Prometheus or the CountyFlow read API.
- Business submission and Worker processing do not depend on any SLO query or alert state.

## 6. Acceptance of the observability implementation

Implementation is accepted only when:

1. Prometheus reports Backend, Worker-1, and Worker-2 targets UP.
2. Recording and alert rule files load without errors.
3. Synthetic bounded metric fixtures prove every alert expression, `for` duration, and traffic guard.
4. A real dispatch changes live families without creating forbidden label names or values.
5. Failure E2E proves Neo4j DOWN/recovery, one Worker DOWN with continuity, Prometheus UNAVAILABLE with business continuity, and Grafana failure isolation.
6. Observability ON still satisfies QPS `>=200`, P95 `<300 ms`, and Error Rate `<0.1%`.
