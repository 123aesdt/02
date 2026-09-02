"""Bounded background sampling for current operational state gauges."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from app.observability.recorder import MetricsRecorder

CURRENT_STATE_GAUGES = frozenset(
    {
        "countyflow_memory_projection_state",
        "countyflow_memory_partial_mutations",
        "countyflow_runtime_threads",
        "countyflow_checkpoint_orphans",
        "countyflow_worker_pending_messages",
        "countyflow_worker_stream_lag",
        "countyflow_worker_dlq_messages",
    }
)


@dataclass(frozen=True)
class GaugeSample:
    metric: str
    value: float
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metric not in CURRENT_STATE_GAUGES:
            raise ValueError(f"Unsupported operational state gauge: {self.metric}")
        if self.value < 0:
            raise ValueError("Operational state gauge values must be non-negative")


SampleSource = Callable[[], Awaitable[tuple[GaugeSample, ...]]]


@dataclass(frozen=True)
class StateSampleResult:
    source: str
    available: bool
    sample_count: int


class OperationalStateSampler:
    """Refresh approved aggregate gauges outside business request transactions."""

    def __init__(
        self,
        sources: Mapping[str, SampleSource],
        metrics: MetricsRecorder,
        *,
        interval_seconds: float,
        timeout_seconds: float,
    ) -> None:
        if interval_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("Sampling interval and timeout must be positive")
        self._sources = dict(sources)
        self._metrics = metrics
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def run_once(self) -> tuple[StateSampleResult, ...]:
        results: list[StateSampleResult] = []
        for source, sample in self._sources.items():
            try:
                values = await asyncio.wait_for(sample(), timeout=self._timeout_seconds)
            except Exception:
                results.append(StateSampleResult(source, False, 0))
                continue
            for value in values:
                self._metrics.set_gauge(value.metric, value.value, value.labels)
            results.append(StateSampleResult(source, True, len(values)))
        return tuple(results)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="countyflow-operational-state-sampler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue
