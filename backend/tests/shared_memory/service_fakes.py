from datetime import UTC, datetime
from decimal import Decimal

from app.graph_memory.models import EntityType, GraphEntity, RelationType
from app.shared_memory.protocols import GraphProjection, VectorProjection
from app.shared_memory.redis_lock import MemoryLockHandle


class FakeMemoryLock:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.acquires = 0
        self.releases = 0

    async def acquire(self, fact_key: str) -> MemoryLockHandle:
        self.acquires += 1
        return MemoryLockHandle(f"countyflow:lock:memory:{fact_key}", "token", self.acquired)

    async def release(self, handle: MemoryLockHandle) -> bool:
        self.releases += 1
        return handle.acquired


class FakeProjectionPort:
    def __init__(self) -> None:
        self.states: dict[tuple[str, int], str] = {}
        self.stage_calls = 0
        self.activate_calls = 0
        self.retire_calls = 0
        self.active_versions: dict[str, set[int]] = {}
        self.fail_stage_code: str | None = None
        self.fail_activate_code: str | None = None

    async def stage(self, projection) -> None:
        self.stage_calls += 1
        if self.fail_stage_code:
            code, self.fail_stage_code = self.fail_stage_code, None
            raise RuntimeError(code)
        self.states[(projection.mutation_id, projection.control_version)] = "STAGED"

    async def probe(self, mutation_id: str, control_version: int) -> str | None:
        return self.states.get((mutation_id, control_version))

    async def activate(self, projection) -> None:
        self.activate_calls += 1
        if self.fail_activate_code:
            code, self.fail_activate_code = self.fail_activate_code, None
            raise RuntimeError(code)
        self.states[(projection.mutation_id, projection.control_version)] = "ACTIVE"
        self.active_versions.setdefault(projection.fact_key, set()).add(projection.control_version)

    async def retire_previous(self, projection) -> None:
        self.retire_calls += 1
        versions = self.active_versions.setdefault(projection.fact_key, set())
        versions.difference_update(version for version in versions if version < projection.control_version)


class FakeProjectionBuilder:
    async def build_vector(self, command, mutation_id: str, fact_key: str, version: int) -> VectorProjection:
        return VectorProjection(
            mutation_id=mutation_id,
            fact_key=fact_key,
            control_version=version,
            memory_id=command.vector_memory_id or fact_key,
            vector=(1.0, 0.0, 0.0, 0.0),
            driver_id=command.subject_id,
            route_id=command.object_id or "unknown-route",
            anomaly_type=command.predicate,
            resolution_text=str(command.value_json.get("resolution", command.value_json)),
            metadata={"text": command.reason},
            expires_at=command.expires_at,
        )

    async def build_graph(self, command, mutation_id: str, fact_key: str, version: int) -> GraphProjection:
        value = next(iter(command.value_json.values()))
        target_type = EntityType(command.object_type) if command.object_type else EntityType.ROAD_CONDITION
        target_id = command.object_id or str(value).strip().lower()
        return GraphProjection(
            mutation_id=mutation_id,
            fact_key=fact_key,
            control_version=version,
            source=GraphEntity(EntityType(command.subject_type), command.subject_id, command.subject_id),
            relation_type=RelationType(command.predicate),
            target=GraphEntity(target_type, target_id, str(value)),
            confidence=command.confidence,
            source_type=command.source_type,
            evidence=command.evidence_text,
            expires_at=command.expires_at,
            timestamp=command.incoming_at,
        )


class FakeMutationEvents:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def publish(self, event_type: str, payload: dict[str, object]) -> None:
        self.events.append((event_type, payload))


def fixed_now() -> datetime:
    return datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


AUTO_THRESHOLD = Decimal("0.7500")
LOWER_DELTA = Decimal("0.1500")
