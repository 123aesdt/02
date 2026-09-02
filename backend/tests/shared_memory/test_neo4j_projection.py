from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.graph_memory.models import EntityType, GraphEntity, RelationType
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.shared_memory.neo4j_projection import Neo4jMemoryProjection
from app.shared_memory.protocols import GraphProjection


class RecordingDriver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def execute_query(self, query, **kwargs):
        self.calls.append((str(query), kwargs))
        return [], object(), tuple()


def projection(version: int) -> GraphProjection:
    return GraphProjection(
        mutation_id=f"00000000-0000-0000-0000-00000000000{version}",
        fact_key="smf_" + "a" * 64,
        control_version=version,
        source=GraphEntity(EntityType.VEHICLE, "vehicle-a", "冷链车A"),
        relation_type=RelationType.STATUS,
        target=GraphEntity(EntityType.ROAD_CONDITION, "broken", "Broken"),
        confidence=Decimal("0.9000"),
        source_type="operator",
        evidence="inspection",
        expires_at=None,
        timestamp=datetime(2026, 8, 27, 1, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_memory_neo4j_retry_no_duplicate() -> None:
    driver = RecordingDriver()
    store = Neo4jMemoryProjection(driver, "neo4j")

    await store.stage(projection(8))
    await store.stage(projection(8))

    relation_calls = [call for call in driver.calls if "MERGE (source)-[r:STATUS" in call[0]]
    assert len(relation_calls) == 2
    assert relation_calls[0][1]["parameters_"]["projection_id"] == relation_calls[1][1]["parameters_"]["projection_id"]
    assert "{projection_id: $projection_id}" in relation_calls[0][0]


@pytest.mark.asyncio
async def test_neo4j_staged_relation_not_recalled() -> None:
    driver = RecordingDriver()
    repository = Neo4jGraphMemoryRepository(driver, "neo4j")

    await repository.find_related(["Vehicle:vehicle-a"], limit=5)
    await repository.find_paths("Vehicle:vehicle-a", max_hops=2, limit=5)

    assert all("projection_status IS NULL" in query for query, _ in driver.calls)
    assert all("projection_status = $active_status" in query for query, _ in driver.calls)
    assert all(options["parameters_"]["active_status"] == "ACTIVE" for _, options in driver.calls)


@pytest.mark.asyncio
async def test_neo4j_activation_retires_previous_version() -> None:
    driver = RecordingDriver()
    store = Neo4jMemoryProjection(driver, "neo4j")
    item = projection(8)

    await store.activate(item)
    await store.retire_previous(item)

    activate_query, activate_options = driver.calls[0]
    retire_query, retire_options = driver.calls[1]
    assert "SET r.projection_status = $active_status" in activate_query
    assert activate_options["parameters_"]["active_status"] == "ACTIVE"
    assert "SET r.projection_status = $retired_status" in retire_query
    assert retire_options["parameters_"]["retired_status"] == "RETIRED"
    assert "$control_version" in retire_query


@pytest.mark.asyncio
async def test_neo4j_projection_uses_allowlists_and_parameterized_values() -> None:
    driver = RecordingDriver()
    store = Neo4jMemoryProjection(driver, "neo4j")
    malicious = projection(8)
    malicious = GraphProjection(**{**malicious.__dict__, "evidence": "'}) MATCH (n) DETACH DELETE n //"})

    await store.stage(malicious)

    relation_query, options = next(call for call in driver.calls if "MERGE (source)-[r:STATUS" in call[0])
    assert malicious.evidence not in relation_query
    assert options["parameters_"]["evidence"] == malicious.evidence

