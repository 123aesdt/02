from datetime import UTC, datetime
from decimal import Decimal

from app.models.shared_memory import SharedMemoryFact


def fact_row(**changes: object) -> SharedMemoryFact:
    values: dict[str, object] = {
        "fact_id": "00000000-0000-0000-0000-000000000001",
        "fact_key": "smf_example",
        "category": "DispatchMemory",
        "fact_kind": "ATTRIBUTE",
        "subject_type": "Vehicle",
        "subject_id": "vehicle-a",
        "predicate": "STATUS",
        "value_json": {"status": "Normal"},
        "content_fingerprint": "a" * 64,
        "version": 1,
        "confidence": Decimal("0.9000"),
        "status": "ACTIVE",
        "vector_memory_id": None,
        "graph_fact_key": "Vehicle:vehicle-a|STATUS|RoadCondition:normal",
        "last_mutation_id": "00000000-0000-0000-0000-000000000002",
        "created_at": datetime(2026, 8, 27, 1, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 8, 27, 1, 0, tzinfo=UTC),
    }
    values.update(changes)
    return SharedMemoryFact(**values)

