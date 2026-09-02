# V2-G1 COMPLETE

**Acceptance date:** 2026-08-28  
**Scope:** Production Observability / Prometheus / Grafana / Frontend Live Monitoring  
**Business topology:** unchanged eight-agent order; observability is best-effort and outside business transactions.

## Result

V2-G1 is VERIFIED. The runtime now declares 11 services and retains 10 long-running services after the one-shot Migration exits successfully. Backend, Worker-1, and Worker-2 expose isolated internal Prometheus registries; Prometheus and Grafana are provisioned from repository configuration; the product Monitoring page reads only typed, authorized, fixed-query API DTOs. Live operations and frozen acceptance baselines remain separate.

## Acceptance matrix

| Area | Result | Evidence |
|---|---|---|
| Metrics abstraction | VERIFIED | `MetricsRecorder`, `PrometheusMetricsRecorder`, `SafeMetricsRecorder`, and `NoOpMetricsRecorder`; recorder failures are swallowed without wrapping business operations. |
| Metric families | VERIFIED | 42 registered families covering HTTP, WebSocket, eight Agents, Environment, Vector/Graph, Shared Memory, Checkpoint, Runtime Override, Worker/Redis, and dependencies. |
| Process/registry lifecycle | VERIFIED | Duplicate construction tests pass; Backend and each Worker own one explicit `:9100` lifecycle; test profile binds no metrics port. |
| Cardinality | VERIFIED | All metric definitions pass the label/value allowlists; task/thread/entity/operator IDs, text, raw paths, reasons, and exceptions are forbidden labels. |
| HTTP / WebSocket | VERIFIED | Route-template HTTP counters, duration and in-flight gauges; bounded WebSocket groups; live subscription and replay regression pass. |
| Eight-Agent | VERIFIED | Intake → Entity Memory → Graph Memory → Environment → Capacity → Routing → Dispatch → Audit all emit bounded execution, duration, and in-flight metrics. |
| Vector / Graph Memory | VERIFIED | Recall/query/result/duration/degradation families present; Graph failure remains safe degradation. |
| Shared Memory | VERIFIED | Mutation, projection lifecycle, unresolved PARTIAL, reconciliation, and projection-leak invariant metrics present. |
| Checkpoint | VERIFIED | Operation/result/duration/payload/orphan/reconciliation metrics present without checkpoint IDs in labels. |
| Runtime Override | VERIFIED | APPLIED/rejected/conflict/partial/failed, duration, bounded conflict reason, and downstream-stale invariant metrics present. |
| Worker / Redis | VERIFIED | Message outcomes, pending, lag, recovery estimate/breach, DLQ, and bounded Redis error metrics present. |
| Dependency probes | VERIFIED | MySQL, Redis, Qdrant, and Neo4j use bounded background probes; failures never execute inside the business path. |
| Structured correlation | VERIFIED | docker-dev/production JSON logging and bounded correlation propagation are implemented; IDs remain logs/audit fields, never metric labels. |
| Prometheus targets | VERIFIED | Backend, Worker-1, and Worker-2 are all `up`; required family metadata is present. See [prometheus-targets.json](raw/prometheus-targets.json). |
| Real metric traffic | VERIFIED | A real approved Dispatch increased Agent executions by `8` and Graph queries by `1`; no global absolute-counter assertion is used. |
| Recording rules | VERIFIED | promtool: 9 rules, PASS. |
| Alert rules | VERIFIED | promtool: 13 rules, PASS; minimum-traffic and `for` guards remain unchanged. |
| Alert E2E | VERIFIED | Real Neo4j outage produced `pending` at `04:13:06Z`, `firing` at `04:15:07Z`, and `resolved` at `04:17:06Z`, with the original `for: 2m`. See [alert-e2e.json](raw/alert-e2e.json). |
| Grafana provisioning | VERIFIED | Health `ok`, datasource UID `countyflow-prometheus`, dashboard UID `countyflow-v2-operations`. See [grafana-provisioning.json](raw/grafana-provisioning.json). |
| Dashboard | VERIFIED | Provisioned SLO, API, Eight-Agent, Worker/Redis, Vector/Graph, Shared Memory, Checkpoint, Runtime Override, and Dependency sections. |
| Observability Read API | VERIFIED | Six GET-only endpoints, `monitor:read`, windows `5m|15m|1h`, fixed query catalog, no arbitrary PromQL. |
| Frontend Monitoring | VERIFIED | `LIVE`, `STALE`, `UNAVAILABLE`, `NO_PERMISSION`; API mode has no Monitoring Mock fallback. Playwright 3/3 PASS. See [browser-e2e.json](raw/browser-e2e.json). |
| Live vs baseline | VERIFIED | Live Prometheus data and `VERIFIED ACCEPTANCE BASELINE` render as separate regions; no acceptance value is published as a live family. |
| Neo4j failure | VERIFIED | Dependency DOWN visible and a new real business task completed through existing Graph degradation; recovery returned UP. |
| Worker failure | VERIFIED | Worker-1 target DOWN, Worker-2 UP and business continuity verified. |
| Prometheus failure | VERIFIED | Read API/UI became UNAVAILABLE while a new real Dispatch still completed; recovery returned live. |
| Grafana failure | VERIFIED | CountyFlow Monitoring remained available through Prometheus while Grafana was stopped; recovery verified. See [failure-e2e.json](raw/failure-e2e.json). |
| OFF/ON performance | VERIFIED | Same real workload in both modes. ON: `971.600 QPS`, API P95 `96.737 ms`, error rate `0`; hard gates are `>=200`, `<300 ms`, `<0.1%`. Graph workflow-event P95 `379.139 ms`, Override HTTP P95 `186.278 ms`, and Worker completed-task throughput `0.474/s` were recorded rather than replaced with zero placeholders. See [overhead.json](raw/overhead.json). |
| Backend regression | VERIFIED | Ruff PASS; `571 passed, 3 skipped` (the three opt-in Real Store tests are covered by Docker acceptance). |
| Frontend regression | VERIFIED | ESLint PASS; `19` files / `82 tests` PASS; production build PASS. |
| Docker | VERIFIED | Compose valid; `11` declared, `10` running, Migration exit `0`, Redis Pending `0`. |
| Launcher | VERIFIED | Full launcher retains the existing entrypoint and starts the 11-service runtime; light local launcher semantics are unchanged. |
| `check.ps1` | VERIFIED | `[OK] All quality gates passed.` |
| Secret safety | VERIFIED | Actual `.env`/`.docker.env` secret-value artifact scan: `0 findings`; both files are Git-ignored. No credential appears in metrics, JSON, Markdown, screenshots, or committed configuration. |
| Git checks | VERIFIED | `git diff --check` and `git diff --cached --check` PASS; status inspected; no commit, merge, PR, or author change performed. |

## Performance deltas

| Metric | OFF | ON | Delta |
|---|---:|---:|---:|
| API P95 | 123.332 ms | 96.737 ms | -21.564% |
| QPS | 937.157 | 971.600 | +3.675% |
| Error rate | 0 | 0 | n/a |
| Graph workflow-event P95 | 1666.632 ms | 379.139 ms | -77.251% |
| Runtime Override HTTP P95 | 175.777 ms | 186.278 ms | +5.974% |
| Worker completed-task throughput | 0.697/s | 0.474/s | -31.994% |

The OFF/ON sample is a small controlled comparison and is reported as measured, including cold-start variance. It does not replace the frozen Graph query acceptance baseline of `20/20`, P95 `10.354 ms`, or the prior Locust baseline.

## Screenshots

- [Monitoring live](screenshots/monitoring-live.png)
- [Grafana SLO overview](screenshots/grafana-slo-overview.png)
- [Grafana Agents](screenshots/grafana-agents.png)
- [Grafana Memory / Runtime](screenshots/grafana-memory-runtime.png)
- [Neo4j dependency down](screenshots/dependency-down.png)
- [Prometheus unavailable](screenshots/prometheus-unavailable.png)

## Regression constraints preserved

The eight-agent order, Qdrant Vector Memory, Neo4j Graph Memory degradation, MySQL Shared Memory Control Plane, official Redis Checkpoint, Runtime Override safety boundary, Redis ACK/retry/DLQ behavior, Dispatch/Audit idempotency, and frozen V2 acceptance results are unchanged. A real final WebSocket business run retained `memory-rain-li → national-102 → REROUTE → APPROVED` evidence and Redis Pending `0`.

## Deferred

Loki, Tempo, Jaeger, OpenTelemetry SDK/Collector, Alertmanager, outbound email/Slack/WeChat/PagerDuty notifications, cAdvisor/exporter containers, Kubernetes, Redis Sentinel, MySQL HA, Qdrant Cluster, Neo4j Cluster, new Agents, and new business algorithms remain out of V2-G1.
