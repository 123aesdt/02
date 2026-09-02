"""Bounded dependency probes that never execute in request transactions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import perf_counter

from app.observability.labels import DEPENDENCIES
from app.observability.recorder import MetricsRecorder

Probe = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class DependencyProbeResult:
    dependency: str
    up: bool
    duration_seconds: float


class DependencyProbeService:
    def __init__(self, probes: Mapping[str, Probe], metrics: MetricsRecorder, *, timeout_seconds: float) -> None:
        unknown = set(probes) - DEPENDENCIES
        if unknown:
            raise ValueError(f"Unknown dependency probes: {sorted(unknown)}")
        self._probes = dict(probes)
        self._metrics = metrics
        self._timeout_seconds = timeout_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def run_once(self) -> tuple[DependencyProbeResult, ...]:
        results: list[DependencyProbeResult] = []
        for dependency, probe in self._probes.items():
            started = perf_counter()
            try:
                await asyncio.wait_for(probe(), timeout=self._timeout_seconds)
                up = True
            except Exception:
                up = False
            duration = perf_counter() - started
            self._metrics.set_gauge("countyflow_dependency_up", 1 if up else 0, {"dependency": dependency})
            self._metrics.observe("countyflow_dependency_probe_duration_seconds", duration, {"dependency": dependency})
            results.append(DependencyProbeResult(dependency, up, duration))
        return tuple(results)

    def start(self, *, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("Probe interval must be positive")
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(interval_seconds), name="countyflow-dependency-probes")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run(self, interval_seconds: float) -> None:
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue
