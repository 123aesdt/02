"""Backend-owned observability probes and aggregate state sampling lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from qdrant_client import QdrantClient
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import build_session_factory
from app.graph_memory.driver import build_neo4j_driver
from app.models.runtime_thread import RuntimeThread
from app.models.shared_memory import MemoryMutation
from app.observability.probes import DependencyProbeService
from app.observability.recorder import MetricsRecorder
from app.observability.sampler import GaugeSample, OperationalStateSampler
from app.runtime_threads.models import RuntimeThreadStatus
from app.shared_memory.models import ProjectionStatus
from app.streams.redis_queue import RedisStreamQueue


@dataclass
class BackendObservabilityRuntime:
    probes: DependencyProbeService
    sampler: OperationalStateSampler
    redis: Redis
    qdrant: QdrantClient
    neo4j: object | None
    session_factory: sessionmaker[Session]
    interval_seconds: float

    def start(self) -> None:
        self.probes.start(interval_seconds=self.interval_seconds)
        self.sampler.start()

    async def stop(self) -> None:
        await self.probes.stop()
        await self.sampler.stop()
        await self.redis.aclose()
        self.qdrant.close()
        if self.neo4j is not None:
            await self.neo4j.close()
        bind = self.session_factory.kw.get("bind")
        if bind is not None:
            bind.dispose()


def build_backend_observability_runtime(settings: Settings, metrics: MetricsRecorder) -> BackendObservabilityRuntime:
    session_factory = build_session_factory(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    qdrant = QdrantClient(settings.qdrant_url)
    neo4j = build_neo4j_driver(settings)
    queue = RedisStreamQueue(
        redis,
        settings.redis_stream_name,
        settings.redis_consumer_group,
        settings.redis_consumer_name,
        dlq_stream_name=settings.redis_dlq_stream_name,
    )

    async def mysql_probe() -> None:
        def check() -> None:
            with session_factory() as session:
                session.execute(select(1)).scalar_one()

        await asyncio.to_thread(check)

    async def redis_probe() -> None:
        if not await redis.ping():
            raise ConnectionError("Redis ping failed")

    async def qdrant_probe() -> None:
        await asyncio.to_thread(qdrant.get_collections)

    async def neo4j_probe() -> None:
        if neo4j is None:
            raise ConnectionError("Neo4j is not configured")
        await neo4j.verify_connectivity()

    async def mysql_samples() -> tuple[GaugeSample, ...]:
        return await asyncio.to_thread(_mysql_state_samples, session_factory)

    async def redis_samples() -> tuple[GaugeSample, ...]:
        state = await queue.get_operational_state()
        samples = [
            GaugeSample("countyflow_worker_stream_lag", state.stream_lag),
            GaugeSample("countyflow_worker_dlq_messages", state.dlq_messages),
        ]
        for worker in ("worker-1", "worker-2"):
            samples.append(
                GaugeSample(
                    "countyflow_worker_pending_messages",
                    state.pending_by_consumer.get(worker, 0),
                    {"worker": worker},
                )
            )
        return tuple(samples)

    probes = DependencyProbeService(
        {"mysql": mysql_probe, "redis": redis_probe, "qdrant": qdrant_probe, "neo4j": neo4j_probe},
        metrics,
        timeout_seconds=settings.observability_probe_timeout_seconds,
    )
    sampler = OperationalStateSampler(
        {"mysql": mysql_samples, "redis": redis_samples},
        metrics,
        interval_seconds=settings.observability_sample_interval_seconds,
        timeout_seconds=settings.observability_probe_timeout_seconds,
    )
    return BackendObservabilityRuntime(
        probes,
        sampler,
        redis,
        qdrant,
        neo4j,
        session_factory,
        settings.observability_sample_interval_seconds,
    )


def _mysql_state_samples(session_factory: sessionmaker[Session]) -> tuple[GaugeSample, ...]:
    samples: list[GaugeSample] = []
    with session_factory() as session:
        thread_counts = dict(session.execute(select(RuntimeThread.status, func.count()).group_by(RuntimeThread.status)).all())
        for status in RuntimeThreadStatus:
            samples.append(GaugeSample("countyflow_runtime_threads", thread_counts.get(status.value, 0), {"result": status.value}))

        partial = session.scalar(select(func.count()).select_from(MemoryMutation).where(MemoryMutation.status == "PARTIAL")) or 0
        samples.append(GaugeSample("countyflow_memory_partial_mutations", partial))
        for store, column in (("qdrant", MemoryMutation.vector_status), ("neo4j", MemoryMutation.graph_status)):
            counts = dict(
                session.execute(
                    select(column, func.count()).where(column.in_(["STAGED", "ACTIVE", "RETIRED"])).group_by(column)
                ).all()
            )
            for projection in (ProjectionStatus.STAGED, ProjectionStatus.ACTIVE, ProjectionStatus.RETIRED):
                samples.append(
                    GaugeSample(
                        "countyflow_memory_projection_state",
                        counts.get(projection.value, 0),
                        {"store": store, "projection": projection.value},
                    )
                )
        checkpoint_orphans = session.scalar(
            select(func.count())
            .select_from(RuntimeThread)
            .where(RuntimeThread.checkpoint_count > 0, RuntimeThread.current_checkpoint_id.is_(None))
        ) or 0
        samples.append(GaugeSample("countyflow_checkpoint_orphans", checkpoint_orphans))
    return tuple(samples)
