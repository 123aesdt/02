import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.probes import DependencyProbeService
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder


@pytest.mark.asyncio
async def test_dependency_metrics() -> None:
    registry = CollectorRegistry()
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))

    async def healthy() -> None:
        return None

    async def unhealthy() -> None:
        raise TimeoutError

    service = DependencyProbeService({"mysql": healthy, "neo4j": unhealthy}, recorder, timeout_seconds=0.05)
    results = await service.run_once()

    assert [(result.dependency, result.up) for result in results] == [("mysql", True), ("neo4j", False)]
    text = generate_latest(registry).decode()
    assert 'countyflow_dependency_up{dependency="mysql"} 1.0' in text
    assert 'countyflow_dependency_up{dependency="neo4j"} 0.0' in text
