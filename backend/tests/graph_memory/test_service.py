import pytest

from app.graph_memory.extractor import DeterministicGraphTripleExtractor, GraphMemoryContext
from app.graph_memory.fake_repository import FakeGraphMemoryRepository
from app.graph_memory.models import EntityType, GraphEntity, GraphRelation, RelationType
from app.graph_memory.service import GraphMemoryService


def _seed_repository() -> FakeGraphMemoryRepository:
    driver = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅")
    route = GraphEntity(EntityType.ROUTE, "xinping-road", "新平路")
    alternate = GraphEntity(EntityType.ROUTE, "national-102", "102国道")
    rain = GraphEntity(EntityType.WEATHER, "rain", "雨天")
    repository = FakeGraphMemoryRepository()
    repository.seed(
        (driver, route, alternate, rain),
        (
            GraphRelation(driver, RelationType.HAS_RISK_ON, route, source_type="seed"),
            GraphRelation(route, RelationType.HIGH_RISK_WHEN, rain, source_type="seed"),
            GraphRelation(alternate, RelationType.ALTERNATIVE_TO, route, source_type="seed"),
        ),
    )
    return repository


@pytest.mark.asyncio
async def test_graph_memory_service_recalls_required_relationship_context():
    service = GraphMemoryService(_seed_repository(), DeterministicGraphTripleExtractor())
    recall = await service.recall(
        GraphMemoryContext(
            driver_id="driver-li",
            vehicle_id="vehicle-cold-a",
            route_id="xinping-road",
            anomaly_type="rain_slippery",
            text="李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。",
        )
    )

    facts = {(fact.source.entity_id, fact.relation_type, fact.target.entity_id) for fact in recall.facts}
    assert ("driver-li", RelationType.HAS_RISK_ON, "xinping-road") in facts
    assert ("xinping-road", RelationType.HIGH_RISK_WHEN, "rain") in facts
    assert ("national-102", RelationType.ALTERNATIVE_TO, "xinping-road") in facts
    assert recall.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_graph_memory_service_returns_bounded_two_hop_paths():
    repository = _seed_repository()
    service = GraphMemoryService(repository, DeterministicGraphTripleExtractor(), max_hops=2, result_limit=10)
    recall = await service.recall(GraphMemoryContext("driver-li", "xinping-road", "rain_slippery", "雨天湿滑"))

    paths = [path.to_dict() for path in recall.paths]
    assert any(
        [entity["entity_id"] for entity in path["entities"]] == ["driver-li", "xinping-road", "rain"]
        for path in paths
    )
    assert all(1 <= len(path["relations"]) <= 2 for path in paths)
    assert len(paths) <= 10


def test_graph_memory_service_rejects_unbounded_search_configuration():
    with pytest.raises(ValueError, match="max_hops"):
        GraphMemoryService(_seed_repository(), DeterministicGraphTripleExtractor(), max_hops=4)
    with pytest.raises(ValueError, match="result_limit"):
        GraphMemoryService(_seed_repository(), DeterministicGraphTripleExtractor(), result_limit=0)

