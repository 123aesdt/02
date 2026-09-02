import json

import pytest

from app.events.broker import InMemoryTaskEventBroker
from app.shared_memory.events import MemoryMutationEventPublisher
from app.shared_memory.models import SharedMemoryMutationCommand
from tests.shared_memory.test_mutation_service import command, harness


@pytest.mark.asyncio
async def test_memory_secret_safety(sqlite_factory) -> None:
    secret = "must-not-leak"
    item = command(
        evidence_text=f"Authorization: Bearer {secret}",
        reason=f"inspection token=Bearer {secret}",
    )
    assert isinstance(item, SharedMemoryMutationCommand)
    service, repository, _, _, events = harness(sqlite_factory)

    result = await service.mutate(item)
    detail = repository.get_fact_detail(result.fact_key)
    serialized = json.dumps({"result": result.to_dict(), "detail": detail, "events": events.events})

    assert secret not in serialized
    assert "[REDACTED]" in serialized


@pytest.mark.asyncio
async def test_memory_event_adapter_reuses_existing_broker_without_sensitive_fields() -> None:
    broker = InMemoryTaskEventBroker()
    publisher = MemoryMutationEventPublisher(broker)

    await publisher.publish(
        "MEMORY_MUTATION_APPLIED",
        {
            "mutation_id": "mutation-1",
            "fact_key": "smf_" + "a" * 64,
            "status": "APPLIED",
            "decision": "CREATE",
        },
    )

    history = await broker.history("mutation-1")
    assert history[0].event_type == "MEMORY_MUTATION_APPLIED"
    assert set(history[0].data) == {"mutation_id", "fact_key", "status", "decision"}

