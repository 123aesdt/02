from app.graph_memory.extractor import DeterministicGraphTripleExtractor, GraphMemoryContext
from app.graph_memory.models import EntityType, RelationType


def test_core_text_extracts_only_explicit_entities_and_relations():
    context = GraphMemoryContext(
        driver_id="driver-li",
        vehicle_id="vehicle-cold-a",
        route_id="xinping-road",
        anomaly_type="rain_slippery",
        text="李师傅驾驶冷链车A，在雨天经过新平路时报告道路湿滑。",
    )

    extraction = DeterministicGraphTripleExtractor().extract(context)
    identities = {(entity.entity_type, entity.entity_id, entity.display_name) for entity in extraction.entities}
    relation_types = {relation.relation_type for relation in extraction.relations}

    assert (EntityType.DRIVER, "driver-li", "李师傅") in identities
    assert (EntityType.VEHICLE, "vehicle-cold-a", "冷链车A") in identities
    assert (EntityType.ROUTE, "xinping-road", "新平路") in identities
    assert (EntityType.WEATHER, "rain", "雨天") in identities
    assert (EntityType.ANOMALY, "rain-slippery", "雨天湿滑") in identities
    assert {RelationType.DRIVES, RelationType.SERVES, RelationType.AFFECTED_BY}.issubset(relation_types)
    assert RelationType.ALTERNATIVE_TO not in relation_types
    assert all(entity.entity_id != "national-102" for entity in extraction.entities)

