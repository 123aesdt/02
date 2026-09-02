import asyncio

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder
from app.observability.sampler import GaugeSample, OperationalStateSampler


@pytest.mark.asyncio
async def test_state_sampler_records_only_successful_bounded_samples() -> None:
    registry = CollectorRegistry()
    recorder = SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry)))
    recorder.set_gauge("countyflow_checkpoint_orphans", 7)

    async def memory_samples() -> tuple[GaugeSample, ...]:
        return (GaugeSample("countyflow_memory_partial_mutations", 3),)

    async def failed_checkpoint_sample() -> tuple[GaugeSample, ...]:
        raise TimeoutError

    sampler = OperationalStateSampler(
        {"memory": memory_samples, "checkpoint": failed_checkpoint_sample},
        recorder,
        interval_seconds=0.01,
        timeout_seconds=0.01,
    )

    results = await sampler.run_once()

    assert [(result.source, result.available) for result in results] == [("memory", True), ("checkpoint", False)]
    text = generate_latest(registry).decode()
    assert "countyflow_memory_partial_mutations 3.0" in text
    assert "countyflow_checkpoint_orphans 7.0" in text


@pytest.mark.asyncio
async def test_state_sampler_start_stop_is_explicit_and_idempotent() -> None:
    calls = 0

    async def sample() -> tuple[GaugeSample, ...]:
        nonlocal calls
        calls += 1
        return ()

    sampler = OperationalStateSampler(
        {"runtime": sample},
        SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(CollectorRegistry()))),
        interval_seconds=0.001,
        timeout_seconds=0.01,
    )

    sampler.start()
    sampler.start()
    await asyncio.sleep(0.01)
    await sampler.stop()
    await sampler.stop()

    assert calls > 0
