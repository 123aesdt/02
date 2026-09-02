import pytest

from app.graph_memory.fake_repository import FakeGraphMemoryRepository
from app.graph_memory.models import RelationType
from app.graph_memory.seed import seed_graph_memory


@pytest.mark.asyncio
async def test_development_seed_is_idempotent_and_contains_only_meaningful_relations():
    repository = FakeGraphMemoryRepository()

    await seed_graph_memory(repository)
    first_counts = (repository.entity_count, repository.relation_count)
    await seed_graph_memory(repository)

    assert first_counts == (7, 5)
    assert (repository.entity_count, repository.relation_count) == first_counts
    vehicle = await repository.get_entity("Vehicle", "vehicle-cold-a")
    facts = await repository.find_related(["Route:xinping-road"], limit=20)
    assert vehicle is not None and vehicle.properties["status"] == "normal"
    assert {fact.relation_type for fact in facts} == {
        RelationType.HAS_RISK_ON,
        RelationType.HIGH_RISK_WHEN,
        RelationType.ALTERNATIVE_TO,
    }

