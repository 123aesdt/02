import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder
from tests.runtime_overrides.test_service import request, service_fixture


@pytest.mark.asyncio
async def test_runtime_override_metrics(sqlite_factory) -> None:
    registry = CollectorRegistry()
    service, *_ = await service_fixture(sqlite_factory)
    service.metrics = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))

    await service.apply("thread-override", request())

    text = generate_latest(registry).decode()
    assert 'countyflow_runtime_overrides_total{result="APPLIED"} 1.0' in text
    assert "countyflow_runtime_override_duration_seconds_count 1.0" in text
