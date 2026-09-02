import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore


class EmptySaver:
    async def aget_tuple(self, config):
        return None


@pytest.mark.asyncio
async def test_checkpoint_metrics() -> None:
    registry = CollectorRegistry()
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))
    store = RedisRuntimeCheckpointStore(EmptySaver(), metrics=recorder)

    assert await store.get_exact("thread-1", "checkpoint-1") is None

    text = generate_latest(registry).decode()
    assert 'countyflow_checkpoint_operations_total{operation="read",result="success"} 1.0' in text
    assert 'countyflow_checkpoint_duration_seconds_count{operation="read"} 1.0' in text
