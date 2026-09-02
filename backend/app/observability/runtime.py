"""Process-local observability bootstrap with one registry and server owner."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from prometheus_client import CollectorRegistry

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder, PrometheusMetricsRecorder, SafeMetricsRecorder
from app.observability.server import MetricsRuntime, ServerFactory


@dataclass(frozen=True)
class ProcessObservability:
    recorder: MetricsRecorder
    runtime: MetricsRuntime
    registry: CollectorRegistry


def build_metrics_runtime(
    enabled: bool,
    host: str,
    port: int,
    *,
    registry: CollectorRegistry | None = None,
    server_factory: ServerFactory | None = None,
) -> MetricsRuntime:
    actual_registry = registry or CollectorRegistry()
    kwargs = {"server_factory": server_factory} if server_factory is not None else {}
    return MetricsRuntime(enabled, host, port, actual_registry, **kwargs)


@lru_cache(maxsize=8)
def get_process_observability(enabled: bool, host: str, port: int) -> ProcessObservability:
    registry = CollectorRegistry()
    runtime = build_metrics_runtime(enabled, host, port, registry=registry)
    if not enabled:
        return ProcessObservability(NoOpMetricsRecorder(), runtime, registry)
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))
    return ProcessObservability(recorder, runtime, registry)
