import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder
from app.streams.models import StreamMessage
from app.workers.dispatch_worker import DispatchWorker
from tests.workers.test_dispatch_worker import _ApprovedGraph, _message, _Queue, _RecoveryQueue, _task


def recorder_and_registry():
    registry = CollectorRegistry()
    return SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry))), registry


@pytest.mark.asyncio
async def test_worker_metrics() -> None:
    recorder, registry = recorder_and_registry()
    queue = _Queue([_message()])
    worker = DispatchWorker(queue, _ApprovedGraph(queue.events), read_count=1, block_ms=1, metrics=recorder)

    await worker.run_once()

    text = generate_latest(registry).decode()
    assert 'countyflow_worker_messages_total{result="processed",worker="worker-1"} 1.0' in text
    assert 'countyflow_worker_messages_total{result="acked",worker="worker-1"} 1.0' in text


@pytest.mark.asyncio
async def test_worker_recovery_slo_counter() -> None:
    recorder, registry = recorder_and_registry()
    message = StreamMessage(
        "7-0",
        _task("task-recovered"),
        2,
        {"stream": "test", "pending_idle_ms_at_claim": "5100"},
    )
    queue = _RecoveryQueue([message])

    async def no_sleep(seconds: float) -> None:
        return None

    worker = DispatchWorker(
        queue,
        _ApprovedGraph(queue.events),
        read_count=1,
        block_ms=1,
        consumer_name="worker-1",
        sleep_func=no_sleep,
        metrics=recorder,
    )

    await worker.recover_once()

    text = generate_latest(registry).decode()
    assert 'countyflow_worker_recovery_slo_breaches_total{worker="worker-1"} 1.0' in text
    assert 'countyflow_worker_messages_total{result="recovered",worker="worker-1"} 1.0' in text
