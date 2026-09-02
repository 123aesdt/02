import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder
from tests.shared_memory.test_mutation_service import command, harness


@pytest.mark.asyncio
async def test_memory_mutation_metrics(sqlite_factory) -> None:
    registry = CollectorRegistry()
    service, *_ = harness(sqlite_factory)
    service.metrics = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))

    await service.mutate(command())

    text = generate_latest(registry).decode()
    assert 'countyflow_memory_mutations_total{decision="CREATE",result="APPLIED"} 1.0' in text


def test_projection_metrics() -> None:
    registry = CollectorRegistry()
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))

    recorder.set_gauge("countyflow_memory_projection_state", 3, {"store": "qdrant", "projection": "ACTIVE"})
    recorder.set_gauge("countyflow_memory_partial_mutations", 1)

    text = generate_latest(registry).decode()
    assert 'countyflow_memory_projection_state{projection="ACTIVE",store="qdrant"} 3.0' in text
    assert "countyflow_memory_partial_mutations 1.0" in text
