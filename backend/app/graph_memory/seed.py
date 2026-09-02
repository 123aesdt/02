from app.graph_memory.models import EntityType, GraphEntity, GraphRelation, RelationType
from app.graph_memory.protocols import GraphMemoryRepository


def development_seed() -> tuple[tuple[GraphEntity, ...], tuple[GraphRelation, ...]]:
    driver = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅")
    vehicle = GraphEntity(EntityType.VEHICLE, "vehicle-cold-a", "冷链车A", {"status": "normal"})
    xinping = GraphEntity(EntityType.ROUTE, "xinping-road", "新平路")
    national_102 = GraphEntity(EntityType.ROUTE, "national-102", "102国道")
    rain = GraphEntity(EntityType.WEATHER, "rain", "雨天")
    anomaly = GraphEntity(EntityType.ANOMALY, "rain-slippery", "雨天湿滑")
    resolution = GraphEntity(EntityType.RESOLUTION, "reroute-national-102", "建议改走102国道")
    relations = (
        GraphRelation(driver, RelationType.DRIVES, vehicle, source_type="development_seed"),
        GraphRelation(driver, RelationType.HAS_RISK_ON, xinping, source_type="development_seed"),
        GraphRelation(xinping, RelationType.HIGH_RISK_WHEN, rain, source_type="development_seed"),
        GraphRelation(national_102, RelationType.ALTERNATIVE_TO, xinping, source_type="development_seed"),
        GraphRelation(anomaly, RelationType.RESOLVED_BY, resolution, source_type="development_seed"),
    )
    return (driver, vehicle, xinping, national_102, rain, anomaly, resolution), relations


async def seed_graph_memory(repository: GraphMemoryRepository) -> None:
    entities, relations = development_seed()
    for entity in entities:
        await repository.upsert_entity(entity)
    for relation in relations:
        await repository.upsert_relation(relation)

