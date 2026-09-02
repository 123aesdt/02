from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import update

from app.models.shared_memory import MemoryEvidence, SharedMemoryFact
from app.shared_memory.identity import build_fact_key, content_fingerprint, evidence_fingerprint
from app.shared_memory.models import MemoryCategory, MemoryFactKind, MemoryTarget, SharedMemoryMutationCommand
from app.shared_memory.policy import MemoryPolicySettings, MemoryVersionConflict
from app.shared_memory.service import (
    MemoryMutationBusy,
    MemoryMutationValidationError,
    SharedMemoryMutationService,
)
from app.shared_memory.sqlalchemy_repository import SqlAlchemyMemoryControlRepository
from tests.shared_memory.factories import fact_row
from tests.shared_memory.service_fakes import (
    AUTO_THRESHOLD,
    LOWER_DELTA,
    FakeMemoryLock,
    FakeMutationEvents,
    FakeProjectionBuilder,
    FakeProjectionPort,
    fixed_now,
)

NOW = datetime(2026, 8, 27, 1, 0, tzinfo=UTC)


def command(**changes: object) -> SharedMemoryMutationCommand:
    values: dict[str, object] = {
        "idempotency_key": f"idem-{uuid4()}",
        "category": MemoryCategory.DISPATCH,
        "fact_kind": MemoryFactKind.ATTRIBUTE,
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Normal"},
        "expected_version": None,
        "confidence": Decimal("0.9000"),
        "incoming_at": NOW,
        "source_type": "operator",
        "source_id": "ops-console",
        "operator_id": "operator-1",
        "human_confirmed": False,
        "reason": "inspection",
        "evidence_text": "vehicle inspected",
        "evidence_observed_at": NOW,
        "targets": frozenset({MemoryTarget.GRAPH}),
    }
    values.update(changes)
    return SharedMemoryMutationCommand(**values)


def harness(sqlite_factory, *, lock=None):
    repository = SqlAlchemyMemoryControlRepository(sqlite_factory)
    vector = FakeProjectionPort()
    graph = FakeProjectionPort()
    events = FakeMutationEvents()
    service = SharedMemoryMutationService(
        repository=repository,
        lock=lock or FakeMemoryLock(),
        policy_settings=MemoryPolicySettings(AUTO_THRESHOLD, LOWER_DELTA),
        vector_projection=vector,
        graph_projection=graph,
        projection_builder=FakeProjectionBuilder(),
        event_publisher=events,
        clock=fixed_now,
    )
    return service, repository, vector, graph, events


def seed_fact(sqlite_factory, item: SharedMemoryMutationCommand, *, version=7, **changes: object) -> None:
    fact_key = build_fact_key(item)
    values = {
        "fact_id": str(uuid4()),
        "fact_key": fact_key,
        "content_fingerprint": content_fingerprint(item),
        "version": version,
        "confidence": Decimal("0.9000"),
        "updated_at": NOW - timedelta(minutes=5),
        "expires_at": None,
        "value_json": item.value_json,
    }
    values.update(changes)
    with sqlite_factory() as session:
        session.add(fact_row(**values))
        session.commit()
        if version != 1:
            session.execute(
                update(SharedMemoryFact)
                .where(SharedMemoryFact.fact_key == fact_key)
                .values(version=version, updated_at=values["updated_at"])
            )
            session.commit()


def seed_duplicate_evidence(sqlite_factory, item: SharedMemoryMutationCommand) -> None:
    with sqlite_factory() as session:
        fact = session.query(SharedMemoryFact).one()
        session.add(
            MemoryEvidence(
                evidence_id=str(uuid4()),
                mutation_id=str(uuid4()),
                fact_id=fact.fact_id,
                evidence_fingerprint=evidence_fingerprint(item),
                source_type=item.source_type,
                source_id=item.source_id,
                evidence_text=item.evidence_text,
                evidence_ref=item.evidence_ref,
                observed_at=item.evidence_observed_at,
                confidence=item.confidence,
                safe_summary="vehicle inspected",
                created_at=NOW,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_memory_create(sqlite_factory) -> None:
    service, repository, vector, graph, events = harness(sqlite_factory)

    result = await service.mutate(command())

    assert (result.decision, result.status, result.after_version) == ("CREATE", "APPLIED", 1)
    assert (vector.stage_calls, graph.stage_calls, graph.activate_calls, graph.retire_calls) == (0, 1, 1, 1)
    assert repository.load_fact(result.fact_key).version == 1
    assert [event[0] for event in events.events] == ["MEMORY_MUTATION_REQUESTED", "MEMORY_MUTATION_APPLIED"]


@pytest.mark.asyncio
async def test_memory_duplicate_noop(sqlite_factory) -> None:
    item = command(expected_version=7)
    seed_fact(sqlite_factory, item)
    seed_duplicate_evidence(sqlite_factory, item)
    service, _, vector, graph, _ = harness(sqlite_factory)

    result = await service.mutate(item)

    assert (result.decision, result.status, result.after_version) == ("NOOP", "APPLIED", 7)
    assert (vector.stage_calls, graph.stage_calls) == (0, 0)


@pytest.mark.asyncio
async def test_memory_merge_evidence(sqlite_factory) -> None:
    item = command(expected_version=7, evidence_text="second inspection")
    seed_fact(sqlite_factory, item)
    service, repository, _, graph, _ = harness(sqlite_factory)

    result = await service.mutate(item)

    assert (result.decision, result.after_version, graph.stage_calls) == ("MERGE", 8, 1)
    assert repository.load_fact(result.fact_key).version == 8


@pytest.mark.asyncio
async def test_memory_replace_expired(sqlite_factory) -> None:
    item = command(expected_version=7, value_json={"status": "Broken"})
    seed_fact(
        sqlite_factory,
        item,
        content_fingerprint="a" * 64,
        expires_at=NOW - timedelta(seconds=1),
    )
    service, _, _, _, _ = harness(sqlite_factory)

    assert (await service.mutate(item)).decision == "REPLACE"


@pytest.mark.asyncio
async def test_memory_human_confirmed_replace(sqlite_factory) -> None:
    item = command(expected_version=7, value_json={"status": "Broken"}, human_confirmed=True)
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, _, _, _ = harness(sqlite_factory)

    assert (await service.mutate(item)).decision == "REPLACE"


@pytest.mark.asyncio
async def test_memory_stale_reject(sqlite_factory) -> None:
    item = command(expected_version=7, value_json={"status": "Broken"}, incoming_at=NOW - timedelta(hours=1))
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64, updated_at=NOW)
    service, _, vector, graph, _ = harness(sqlite_factory)

    result = await service.mutate(item)

    assert (result.decision, result.status) == ("REJECT", "REJECTED")
    assert (vector.stage_calls, graph.stage_calls) == (0, 0)


@pytest.mark.asyncio
async def test_memory_lower_confidence_reject(sqlite_factory) -> None:
    item = command(expected_version=7, value_json={"status": "Broken"}, confidence=Decimal("0.7500"))
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, _, _, _, _ = harness(sqlite_factory)

    assert (await service.mutate(item)).decision == "REJECT"


@pytest.mark.asyncio
async def test_memory_conflict_requires_review(sqlite_factory) -> None:
    item = command(expected_version=7, value_json={"status": "Broken"}, confidence=Decimal("0.8500"))
    seed_fact(sqlite_factory, item, content_fingerprint="a" * 64)
    service, repository, _, graph, _ = harness(sqlite_factory)

    result = await service.mutate(item)

    assert (result.decision, result.status, graph.stage_calls) == ("CONFLICT_REVIEW", "CONFLICT", 0)
    assert repository.load_fact(result.fact_key).version == 7


@pytest.mark.asyncio
async def test_memory_low_confidence_requires_review(sqlite_factory) -> None:
    item = command(confidence=Decimal("0.7400"))
    service, repository, _, graph, _ = harness(sqlite_factory)

    result = await service.mutate(item)

    assert (result.decision, result.status, graph.stage_calls) == ("CONFLICT_REVIEW", "CONFLICT", 0)
    assert repository.load_fact(result.fact_key).status == "PENDING_REVIEW"


@pytest.mark.asyncio
async def test_memory_expected_version_conflict(sqlite_factory) -> None:
    item = command(expected_version=6)
    seed_fact(sqlite_factory, item, version=7)
    service, _, _, graph, _ = harness(sqlite_factory)

    with pytest.raises(MemoryVersionConflict):
        await service.mutate(item)
    assert graph.stage_calls == 0


@pytest.mark.asyncio
async def test_memory_mutation_lock(sqlite_factory) -> None:
    service, _, _, _, _ = harness(sqlite_factory, lock=FakeMemoryLock(acquired=False))

    with pytest.raises(MemoryMutationBusy):
        await service.mutate(command())


@pytest.mark.asyncio
async def test_non_dispatch_category_is_rejected_before_lock(sqlite_factory) -> None:
    lock = FakeMemoryLock()
    service, _, _, _, _ = harness(sqlite_factory, lock=lock)

    with pytest.raises(MemoryMutationValidationError):
        await service.mutate(command(category=MemoryCategory.CHAT))
    assert lock.acquires == 0
