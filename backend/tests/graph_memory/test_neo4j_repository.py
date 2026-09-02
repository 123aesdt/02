import pytest
from neo4j.exceptions import ServiceUnavailable

from app.graph_memory.models import EntityType, GraphEntity, GraphRelation, RelationType
from app.graph_memory.neo4j_repository import Neo4jGraphMemoryRepository
from app.graph_memory.protocols import GraphMemoryError
from app.graph_memory.schema import GRAPH_SCHEMA_STATEMENTS, bootstrap_graph_schema


class RecordingDriver:
    def __init__(self, records=None):
        self.calls = []
        self.records = records or []

    async def execute_query(self, query, **kwargs):
        self.calls.append((str(query), kwargs))
        return self.records, object(), tuple()


class UnavailableDriver:
    async def execute_query(self, query, **kwargs):
        raise ServiceUnavailable("neo4j unavailable")


@pytest.mark.asyncio
async def test_driver_connectivity_error_is_normalized_for_safe_agent_degradation():
    repository = Neo4jGraphMemoryRepository(UnavailableDriver(), "neo4j", query_timeout_seconds=0.5)

    with pytest.raises(GraphMemoryError, match="Graph memory store operation failed"):
        await repository.get_entity("Driver", "driver-li")


@pytest.mark.asyncio
async def test_entity_upsert_uses_allowlisted_label_and_parameterized_values():
    driver = RecordingDriver()
    repository = Neo4jGraphMemoryRepository(driver, "neo4j", query_timeout_seconds=0.5)
    malicious_id = "driver-li'}) MATCH (n) DETACH DELETE n //"

    await repository.upsert_entity(GraphEntity(EntityType.DRIVER, malicious_id, "李师傅"))

    query, options = driver.calls[0]
    assert ":Driver" in query
    assert malicious_id not in query
    assert options["parameters_"]["entity_id"] == malicious_id
    assert options["database_"] == "neo4j"


@pytest.mark.asyncio
async def test_relation_upsert_uses_allowlisted_type_and_parameterized_values():
    driver = RecordingDriver()
    repository = Neo4jGraphMemoryRepository(driver, "neo4j")
    source = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅")
    target = GraphEntity(EntityType.ROUTE, "xinping-road", "新平路")

    await repository.upsert_relation(
        GraphRelation(source, RelationType.HAS_RISK_ON, target, evidence="用户值 ' }) MATCH (n) //")
    )

    query, options = driver.calls[0]
    assert "[r:HAS_RISK_ON]" in query
    assert "用户值" not in query
    assert options["parameters_"]["evidence"].startswith("用户值")


@pytest.mark.asyncio
async def test_path_query_is_bounded_and_maps_to_domain_values():
    records = [
        {
            "entities": [
                {"entity_type": "Driver", "entity_id": "driver-li", "display_name": "李师傅", "properties_json": "{}"},
                {"entity_type": "Route", "entity_id": "xinping-road", "display_name": "新平路", "properties_json": "{}"},
            ],
            "relations": [
                {
                    "source_key": "Driver:driver-li",
                    "target_key": "Route:xinping-road",
                    "relation_type": "HAS_RISK_ON",
                    "confidence": 1.0,
                    "source_type": "seed",
                    "evidence": None,
                    "version": 1,
                    "timestamp": "2026-08-26T00:00:00+00:00",
                }
            ],
        }
    ]
    driver = RecordingDriver(records)
    repository = Neo4jGraphMemoryRepository(driver, "neo4j")

    paths = await repository.find_paths("Driver:driver-li", max_hops=2, limit=5)

    query, options = driver.calls[0]
    assert "[*1..2]" in query
    assert "[*]" not in query
    assert options["parameters_"] == {
        "start_key": "Driver:driver-li",
        "active_status": "ACTIVE",
        "limit": 5,
    }
    assert paths[0].relations[0].relation_type == RelationType.HAS_RISK_ON
    assert paths[0].entities[1].entity_id == "xinping-road"


@pytest.mark.asyncio
async def test_related_query_preserves_stored_relationship_direction():
    driver = RecordingDriver()
    repository = Neo4jGraphMemoryRepository(driver, "neo4j")

    await repository.find_related(["Route:xinping-road"], limit=5)

    query, _ = driver.calls[0]
    assert "startNode(r) AS source" in query
    assert "endNode(r) AS target" in query


@pytest.mark.asyncio
async def test_schema_bootstrap_is_repeatable_and_non_destructive():
    driver = RecordingDriver()

    await bootstrap_graph_schema(driver, "neo4j")
    await bootstrap_graph_schema(driver, "neo4j")

    assert len(driver.calls) == len(GRAPH_SCHEMA_STATEMENTS) * 2
    assert all("IF NOT EXISTS" in query for query, _ in driver.calls)
    assert all("DROP" not in query and "DELETE" not in query for query, _ in driver.calls)
