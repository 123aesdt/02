"""Closed PromQL catalog; raw expressions are never accepted."""

from enum import StrEnum


class UnknownObservabilityQuery(ValueError):
    pass


class ObservabilityQueryKey(StrEnum):
    HTTP_QPS = "http_qps"
    HTTP_P95 = "http_p95"
    HTTP_ERROR_RATE = "http_error_rate"
    AGENT_P95 = "agent_p95"
    WORKER_PENDING = "worker_pending"
    WORKER_LAG = "worker_lag"
    GRAPH_P95 = "graph_p95"
    CHECKPOINT_P95 = "checkpoint_p95"
    OVERRIDE_SUCCESS = "override_success"
    MEMORY_PARTIAL = "memory_partial"
    DEPENDENCY_UP = "dependency_up"


_QUERIES = {
    ObservabilityQueryKey.HTTP_QPS: "countyflow:slo:http_qps_5m",
    ObservabilityQueryKey.HTTP_P95: "countyflow:slo:http_p95_5m",
    ObservabilityQueryKey.HTTP_ERROR_RATE: "countyflow:slo:http_error_ratio_5m",
    ObservabilityQueryKey.AGENT_P95: "countyflow:slo:agent_p95_5m",
    ObservabilityQueryKey.WORKER_PENDING: "countyflow:slo:worker_pending",
    ObservabilityQueryKey.WORKER_LAG: "countyflow:slo:worker_stream_lag",
    ObservabilityQueryKey.GRAPH_P95: "countyflow:slo:graph_p95_5m",
    ObservabilityQueryKey.CHECKPOINT_P95: "countyflow:slo:checkpoint_p95_5m",
    ObservabilityQueryKey.OVERRIDE_SUCCESS: "countyflow:slo:override_success_ratio_15m",
    ObservabilityQueryKey.MEMORY_PARTIAL: "countyflow_memory_partial_mutations",
    ObservabilityQueryKey.DEPENDENCY_UP: "countyflow_dependency_up",
}


def resolve_query(key: ObservabilityQueryKey, window: str) -> str:
    if not isinstance(key, ObservabilityQueryKey) or window not in {"5m", "15m", "1h"}:
        raise UnknownObservabilityQuery
    return _QUERIES[key]
