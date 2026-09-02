"""Safe aggregate read model over the fixed Prometheus query catalog."""

import asyncio
from datetime import UTC, datetime

from app.observability.labels import AGENTS, DEPENDENCIES, WORKERS
from app.observability.models import ObservabilityState, ObservabilitySummary
from app.observability.prometheus import PrometheusQueryClient, PrometheusQueryError, PrometheusSample
from app.observability.query_catalog import ObservabilityQueryKey


class ObservabilityUnavailable(Exception):
    pass


class ObservabilityReadService:
    def __init__(self, client: PrometheusQueryClient, *, grafana_url: str | None = None) -> None:
        self._client = client
        self._grafana_url = grafana_url

    async def summary(self, window: str) -> ObservabilitySummary:
        keys = tuple(ObservabilityQueryKey)
        try:
            groups = await asyncio.gather(*(self._client.instant(key, window) for key in keys))
        except PrometheusQueryError:
            raise ObservabilityUnavailable from None
        samples = [sample for group in groups for sample in group]
        if not samples:
            raise ObservabilityUnavailable
        now = datetime.now(UTC).timestamp()
        age = now - max(sample.timestamp for sample in samples)
        if age > 120:
            raise ObservabilityUnavailable
        state = ObservabilityState.LIVE if age <= 45 and all(groups) else ObservabilityState.STALE
        metrics: dict[str, float | None] = {}
        series: dict[str, dict[str, float]] = {}
        for key, group in zip(keys, groups, strict=True):
            values = [sample.value for sample in group]
            metrics[key.value] = (min(values) if key is ObservabilityQueryKey.DEPENDENCY_UP else max(values)) if values else None
            bounded = _bounded_series(key, group)
            if bounded:
                series[key.value] = bounded
        return ObservabilitySummary(state, window, datetime.now(UTC).isoformat(), metrics, self._grafana_url, series)


def _bounded_series(key: ObservabilityQueryKey, samples: tuple[PrometheusSample, ...]) -> dict[str, float]:
    dimension_and_values = {
        ObservabilityQueryKey.AGENT_P95: ("agent", AGENTS),
        ObservabilityQueryKey.WORKER_PENDING: ("worker", WORKERS),
        ObservabilityQueryKey.DEPENDENCY_UP: ("dependency", DEPENDENCIES),
    }.get(key)
    if dimension_and_values is None:
        return {}
    dimension, allowed = dimension_and_values
    result: dict[str, float] = {}
    for sample in samples:
        label = sample.labels.get(dimension)
        if label in allowed:
            result[label] = sample.value
    return result
