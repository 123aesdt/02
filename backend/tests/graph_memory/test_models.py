import json
from dataclasses import FrozenInstanceError

import pytest

from app.graph_memory.models import EntityType, GraphEntity, GraphMemoryRecall, GraphPath, GraphRelation, RelationType


def test_graph_entity_rejects_non_allowlisted_type_and_is_frozen_serializable():
    with pytest.raises(ValueError, match="Unsupported graph entity type"):
        GraphEntity("Driver) MATCH (n) DETACH DELETE n //", "driver-li", "李师傅")

    entity = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅", {"region": "county-a"})
    with pytest.raises(FrozenInstanceError):
        entity.entity_id = "attacker"
    assert json.loads(json.dumps(entity.to_dict(), ensure_ascii=False))["display_name"] == "李师傅"


def test_graph_relation_rejects_non_allowlisted_type_and_validates_confidence():
    source = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅")
    target = GraphEntity(EntityType.ROUTE, "xinping-road", "新平路")

    with pytest.raises(ValueError, match="Unsupported graph relation type"):
        GraphRelation(source, "DRIVES]->(n) DETACH DELETE n //", target)
    with pytest.raises(ValueError, match="confidence"):
        GraphRelation(source, RelationType.HAS_RISK_ON, target, confidence=1.1)


def test_graph_path_and_recall_do_not_expose_infrastructure_objects():
    driver = GraphEntity(EntityType.DRIVER, "driver-li", "李师傅")
    route = GraphEntity(EntityType.ROUTE, "xinping-road", "新平路")
    relation = GraphRelation(driver, RelationType.HAS_RISK_ON, route, source_type="seed")
    path = GraphPath((driver, route), (relation,))
    recall = GraphMemoryRecall((driver,), (relation,), (path,), elapsed_ms=2.5)

    payload = recall.to_dict()
    json.dumps(payload, ensure_ascii=False)
    assert payload["paths"][0]["relations"][0]["relation_type"] == "HAS_RISK_ON"
    assert set(payload) == {"query_entities", "facts", "paths", "elapsed_ms"}

