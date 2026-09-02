"""Canonical Prometheus metric definitions and process-local registration."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Literal
from weakref import WeakKeyDictionary

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.observability.labels import AGENTS, DEPENDENCIES, METRIC_LABEL_ALLOWLIST, SECURITY_ROUTE_CLASSES, WORKERS

MetricKind = Literal["counter", "gauge", "histogram"]
Collector = Counter | Gauge | Histogram

HTTP_BUCKETS = (0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5)
AGENT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.3, 0.5, 1, 2.5)
ENVIRONMENT_BUCKETS = (0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1, 2.5)
MEMORY_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1)
CHECKPOINT_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)
PAYLOAD_BUCKETS = (1024, 4096, 16384, 65536, 262144, 524288, 1048576)
OVERRIDE_BUCKETS = (0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2.5)
RECOVERY_BUCKETS = (0.25, 0.5, 1, 2, 3, 4, 5, 7.5, 10)
PROBE_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1)


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    kind: MetricKind
    labels: tuple[str, ...] = ()
    buckets: tuple[float, ...] = ()
    allowed_values: tuple[tuple[str, frozenset[str]], ...] = ()

    def values_for(self, label: str) -> frozenset[str] | None:
        return dict(self.allowed_values).get(label)


def _values(**values: frozenset[str]) -> tuple[tuple[str, frozenset[str]], ...]:
    return tuple(values.items())


DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "countyflow_http_requests_total",
        "counter",
        ("method", "route_template", "status_class"),
        allowed_values=_values(method=frozenset({"GET", "POST", "OPTIONS", "OTHER"}), status_class=frozenset({"2xx", "3xx", "4xx", "5xx"})),
    ),
    MetricDefinition(
        "countyflow_http_request_duration_seconds",
        "histogram",
        ("method", "route_template"),
        HTTP_BUCKETS,
        _values(method=frozenset({"GET", "POST", "OPTIONS", "OTHER"})),
    ),
    MetricDefinition("countyflow_http_inflight_requests", "gauge"),
    MetricDefinition(
        "countyflow_authentication_failures_total",
        "counter",
        ("reason_code", "route_class"),
        allowed_values=_values(
            reason_code=frozenset({"missing", "invalid", "expired", "provider_unavailable"}),
            route_class=SECURITY_ROUTE_CLASSES,
        ),
    ),
    MetricDefinition(
        "countyflow_authorization_denied_total",
        "counter",
        ("reason_code", "route_class"),
        allowed_values=_values(
            reason_code=frozenset({"permission"}),
            route_class=SECURITY_ROUTE_CLASSES,
        ),
    ),
    MetricDefinition(
        "countyflow_rate_limit_exceeded_total",
        "counter",
        ("reason_code", "route_class"),
        allowed_values=_values(
            reason_code=frozenset({"limit", "control_unavailable"}),
            route_class=SECURITY_ROUTE_CLASSES,
        ),
    ),
    MetricDefinition(
        "countyflow_ws_ticket_rejected_total",
        "counter",
        ("reason_code", "route_class"),
        allowed_values=_values(
            reason_code=frozenset(
                {"missing", "invalid", "wrong_scope", "permission", "expired_replayed", "control_unavailable"}
            ),
            route_class=SECURITY_ROUTE_CLASSES,
        ),
    ),
    MetricDefinition("countyflow_application_errors_total", "counter", ("operation", "reason_code")),
    MetricDefinition("countyflow_websocket_connections", "gauge"),
    MetricDefinition(
        "countyflow_websocket_events_total",
        "counter",
        ("event_type", "result"),
        allowed_values=_values(
            event_type=frozenset({"task", "agent", "memory", "thread", "override", "terminal"}), result=frozenset({"sent", "replayed", "resync", "error"})
        ),
    ),
    MetricDefinition(
        "countyflow_agent_executions_total",
        "counter",
        ("agent", "result"),
        allowed_values=_values(agent=AGENTS, result=frozenset({"success", "review_required", "degraded", "error", "cancelled"})),
    ),
    MetricDefinition("countyflow_agent_duration_seconds", "histogram", ("agent",), AGENT_BUCKETS, _values(agent=AGENTS)),
    MetricDefinition("countyflow_agent_inflight", "gauge", ("agent",), allowed_values=_values(agent=AGENTS)),
    MetricDefinition(
        "countyflow_environment_requests_total",
        "counter",
        ("operation", "result"),
        allowed_values=_values(operation=frozenset({"primary", "fallback"}), result=frozenset({"success", "error"})),
    ),
    MetricDefinition(
        "countyflow_environment_duration_seconds", "histogram", ("operation",), ENVIRONMENT_BUCKETS, _values(operation=frozenset({"primary", "fallback"}))
    ),
    MetricDefinition(
        "countyflow_environment_fallback_total",
        "counter",
        ("reason_code",),
        allowed_values=_values(reason_code=frozenset({"timeout", "http_error", "circuit_open", "invalid_response"})),
    ),
    MetricDefinition("countyflow_vector_recall_total", "counter", ("result",), allowed_values=_values(result=frozenset({"hit", "miss", "error"}))),
    MetricDefinition("countyflow_vector_recall_duration_seconds", "histogram", buckets=MEMORY_BUCKETS),
    MetricDefinition(
        "countyflow_graph_queries_total",
        "counter",
        ("operation", "result"),
        allowed_values=_values(operation=frozenset({"entity", "relation", "path", "multi_hop"}), result=frozenset({"success", "empty", "error"})),
    ),
    MetricDefinition(
        "countyflow_graph_query_duration_seconds",
        "histogram",
        ("operation",),
        MEMORY_BUCKETS,
        _values(operation=frozenset({"entity", "relation", "path", "multi_hop"})),
    ),
    MetricDefinition(
        "countyflow_graph_memory_degraded_total",
        "counter",
        ("reason_code",),
        allowed_values=_values(reason_code=frozenset({"unavailable", "timeout", "query_error", "invalid_result"})),
    ),
    MetricDefinition(
        "countyflow_memory_mutations_total",
        "counter",
        ("decision", "result"),
        allowed_values=_values(
            decision=frozenset({"CREATE", "MERGE", "REPLACE", "REJECT", "CONFLICT_REVIEW", "NOOP"}),
            result=frozenset({"APPLIED", "PARTIAL", "CONFLICT", "FAILED", "REJECTED"}),
        ),
    ),
    MetricDefinition(
        "countyflow_memory_projection_state",
        "gauge",
        ("store", "projection"),
        allowed_values=_values(store=frozenset({"qdrant", "neo4j"}), projection=frozenset({"STAGED", "FINALIZING", "ACTIVE", "RETIRED"})),
    ),
    MetricDefinition("countyflow_memory_partial_mutations", "gauge"),
    MetricDefinition(
        "countyflow_memory_reconciliations_total", "counter", ("result",), allowed_values=_values(result=frozenset({"success", "conflict", "failed", "noop"}))
    ),
    MetricDefinition("countyflow_memory_projection_leaks_total", "counter", ("store",), allowed_values=_values(store=frozenset({"qdrant", "neo4j"}))),
    MetricDefinition(
        "countyflow_runtime_threads", "gauge", ("result",), allowed_values=_values(result=frozenset({"RUNNING", "STABLE", "OVERRIDING", "TERMINAL"}))
    ),
    MetricDefinition(
        "countyflow_checkpoint_operations_total",
        "counter",
        ("operation", "result"),
        allowed_values=_values(operation=frozenset({"write", "read", "promote", "resume", "reconcile"}), result=frozenset({"success", "error", "conflict"})),
    ),
    MetricDefinition(
        "countyflow_checkpoint_duration_seconds",
        "histogram",
        ("operation",),
        CHECKPOINT_BUCKETS,
        _values(operation=frozenset({"write", "read", "promote", "resume", "reconcile"})),
    ),
    MetricDefinition("countyflow_checkpoint_payload_bytes", "histogram", buckets=PAYLOAD_BUCKETS),
    MetricDefinition("countyflow_checkpoint_orphans", "gauge"),
    MetricDefinition(
        "countyflow_checkpoint_reconciliation_total",
        "counter",
        ("result",),
        allowed_values=_values(result=frozenset({"success", "conflict", "failed", "noop"})),
    ),
    MetricDefinition(
        "countyflow_runtime_overrides_total",
        "counter",
        ("result",),
        allowed_values=_values(result=frozenset({"APPLIED", "REJECTED", "CONFLICT", "PARTIAL", "FAILED"})),
    ),
    MetricDefinition("countyflow_runtime_override_duration_seconds", "histogram", buckets=OVERRIDE_BUCKETS),
    MetricDefinition(
        "countyflow_runtime_override_conflicts_total",
        "counter",
        ("reason_code",),
        allowed_values=_values(reason_code=frozenset({"version", "busy", "not_stable", "precondition", "terminal", "permission"})),
    ),
    MetricDefinition("countyflow_runtime_override_downstream_stale_total", "counter"),
    MetricDefinition(
        "countyflow_worker_messages_total",
        "counter",
        ("worker", "result"),
        allowed_values=_values(worker=WORKERS, result=frozenset({"processed", "acked", "retried", "recovered", "dlq", "failed"})),
    ),
    MetricDefinition("countyflow_worker_pending_messages", "gauge", ("worker",), allowed_values=_values(worker=WORKERS)),
    MetricDefinition("countyflow_worker_stream_lag", "gauge"),
    MetricDefinition("countyflow_worker_recovery_duration_seconds", "histogram", ("worker",), RECOVERY_BUCKETS, _values(worker=WORKERS)),
    MetricDefinition("countyflow_worker_recovery_slo_breaches_total", "counter", ("worker",), allowed_values=_values(worker=WORKERS)),
    MetricDefinition("countyflow_worker_dlq_total", "counter", ("worker",), allowed_values=_values(worker=WORKERS)),
    MetricDefinition("countyflow_worker_dlq_messages", "gauge"),
    MetricDefinition(
        "countyflow_redis_operation_errors_total",
        "counter",
        ("operation",),
        allowed_values=_values(operation=frozenset({"stream_read", "stream_ack", "lock", "event", "checkpoint"})),
    ),
    MetricDefinition("countyflow_dependency_up", "gauge", ("dependency",), allowed_values=_values(dependency=DEPENDENCIES)),
    MetricDefinition("countyflow_dependency_probe_duration_seconds", "histogram", ("dependency",), PROBE_BUCKETS, _values(dependency=DEPENDENCIES)),
)


class MetricCatalog:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self.definitions = DEFINITIONS
        self.collectors: dict[str, Collector] = {}
        for definition in self.definitions:
            if not set(definition.labels) <= METRIC_LABEL_ALLOWLIST:
                raise ValueError(f"Metric {definition.name} contains a forbidden label")
            kwargs: dict[str, object] = {"registry": registry, "labelnames": definition.labels}
            if definition.kind == "counter":
                collector = Counter(definition.name, definition.name, **kwargs)
            elif definition.kind == "gauge":
                collector = Gauge(definition.name, definition.name, **kwargs)
            else:
                collector = Histogram(definition.name, definition.name, buckets=definition.buckets, **kwargs)
            self.collectors[definition.name] = collector
        self._by_name = {definition.name: definition for definition in self.definitions}

    def family_names(self) -> set[str]:
        return set(self.collectors)

    def definition(self, name: str) -> MetricDefinition:
        try:
            return self._by_name[name]
        except KeyError as error:
            raise KeyError(f"Unknown metric family: {name}") from error


_catalogs: WeakKeyDictionary[CollectorRegistry, MetricCatalog] = WeakKeyDictionary()
_catalog_lock = RLock()


def build_metric_catalog(registry: CollectorRegistry) -> MetricCatalog:
    """Return the one CountyFlow catalog registered for this process registry."""
    with _catalog_lock:
        catalog = _catalogs.get(registry)
        if catalog is None:
            catalog = MetricCatalog(registry)
            _catalogs[registry] = catalog
        return catalog
