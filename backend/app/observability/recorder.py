"""Narrow, failure-isolated metrics facade for application code."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from app.observability.catalog import MetricCatalog


class MetricLabelError(ValueError):
    """Raised before an unbounded or malformed label reaches Prometheus."""


class MetricsRecorder(Protocol):
    def increment(self, metric: str, labels: Mapping[str, str] | None = None, amount: float = 1) -> None: ...
    def observe(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None: ...
    def set_gauge(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None: ...
    def adjust_gauge(self, metric: str, amount: float, labels: Mapping[str, str] | None = None) -> None: ...
    def observe_agent(self, agent: str, result: str, seconds: float) -> None: ...


class NoOpMetricsRecorder:
    def increment(self, metric: str, labels: Mapping[str, str] | None = None, amount: float = 1) -> None:
        return None

    def observe(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        return None

    def set_gauge(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        return None

    def adjust_gauge(self, metric: str, amount: float, labels: Mapping[str, str] | None = None) -> None:
        return None

    def observe_agent(self, agent: str, result: str, seconds: float) -> None:
        return None


class PrometheusMetricsRecorder:
    def __init__(self, catalog: MetricCatalog) -> None:
        self.catalog = catalog

    def _collector(self, metric: str, labels: Mapping[str, str] | None):
        definition = self.catalog.definition(metric)
        actual = dict(labels or {})
        if set(actual) != set(definition.labels):
            raise MetricLabelError(f"{metric} labels must be exactly {definition.labels}")
        for label, value in actual.items():
            allowed = definition.values_for(label)
            if allowed is not None and value not in allowed:
                raise MetricLabelError(f"Invalid {label} label for {metric}: {value}")
        collector = self.catalog.collectors[metric]
        return collector.labels(**actual) if actual else collector

    def increment(self, metric: str, labels: Mapping[str, str] | None = None, amount: float = 1) -> None:
        self._collector(metric, labels).inc(amount)

    def observe(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._collector(metric, labels).observe(value)

    def set_gauge(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._collector(metric, labels).set(value)

    def adjust_gauge(self, metric: str, amount: float, labels: Mapping[str, str] | None = None) -> None:
        collector = self._collector(metric, labels)
        collector.inc(amount) if amount >= 0 else collector.dec(-amount)

    def observe_agent(self, agent: str, result: str, seconds: float) -> None:
        self.increment("countyflow_agent_executions_total", {"agent": agent, "result": result})
        self.observe("countyflow_agent_duration_seconds", seconds, {"agent": agent})


class SafeMetricsRecorder:
    """Contain every instrumentation failure outside the business path."""

    def __init__(self, delegate: MetricsRecorder, logger: logging.Logger | None = None) -> None:
        self.delegate = delegate
        self.logger = logger or logging.getLogger(__name__)

    def _safe(self, method: str, *args: object, **kwargs: object) -> None:
        try:
            getattr(self.delegate, method)(*args, **kwargs)
        except Exception:
            self.logger.debug("metrics_record_failed", extra={"error_code": "METRICS_RECORD_FAILED"})

    def increment(self, metric: str, labels: Mapping[str, str] | None = None, amount: float = 1) -> None:
        self._safe("increment", metric, labels, amount)

    def observe(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._safe("observe", metric, value, labels)

    def set_gauge(self, metric: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._safe("set_gauge", metric, value, labels)

    def adjust_gauge(self, metric: str, amount: float, labels: Mapping[str, str] | None = None) -> None:
        self._safe("adjust_gauge", metric, amount, labels)

    def observe_agent(self, agent: str, result: str, seconds: float) -> None:
        self._safe("observe_agent", agent, result, seconds)
