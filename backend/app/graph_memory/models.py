import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EntityType(StrEnum):
    DRIVER = "Driver"
    VEHICLE = "Vehicle"
    ROUTE = "Route"
    WEATHER = "Weather"
    ROAD_CONDITION = "RoadCondition"
    STATION = "Station"
    ANOMALY = "Anomaly"
    RESOLUTION = "Resolution"
    DISPATCH_ORDER = "DispatchOrder"
    POLICY_RULE = "PolicyRule"
    USER_PREFERENCE = "UserPreference"


class RelationType(StrEnum):
    DRIVES = "DRIVES"
    SERVES = "SERVES"
    HAS_RISK_ON = "HAS_RISK_ON"
    AFFECTED_BY = "AFFECTED_BY"
    HIGH_RISK_WHEN = "HIGH_RISK_WHEN"
    ALTERNATIVE_TO = "ALTERNATIVE_TO"
    RESOLVED_BY = "RESOLVED_BY"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    DEPENDS_ON = "DEPENDS_ON"
    STATUS = "STATUS"


def _enum_value(value: object, enum_type: type[StrEnum], description: str) -> StrEnum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Unsupported graph {description}: {value!r}") from error


@dataclass(frozen=True)
class GraphEntity:
    entity_type: EntityType | str
    entity_id: str
    display_name: str
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "entity_type", _enum_value(self.entity_type, EntityType, "entity type"))
        if not self.entity_id.strip():
            raise ValueError("Graph entity_id must not be empty")
        if not self.display_name.strip():
            raise ValueError("Graph display_name must not be empty")
        copied = dict(self.properties)
        try:
            json.dumps(copied)
        except (TypeError, ValueError) as error:
            raise ValueError("Graph entity properties must be JSON serializable") from error
        object.__setattr__(self, "properties", copied)

    @property
    def entity_key(self) -> str:
        return f"{self.entity_type.value}:{self.entity_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "display_name": self.display_name,
            "properties": dict(self.properties),
        }


@dataclass(frozen=True)
class GraphRelation:
    source: GraphEntity
    relation_type: RelationType | str
    target: GraphEntity
    confidence: float = 1.0
    source_type: str = "domain"
    evidence: str | None = None
    version: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        object.__setattr__(self, "relation_type", _enum_value(self.relation_type, RelationType, "relation type"))
        if not 0 <= self.confidence <= 1:
            raise ValueError("Graph relation confidence must be between 0 and 1")
        if self.version < 1:
            raise ValueError("Graph relation version must be positive")

    @property
    def relation_key(self) -> str:
        return f"{self.source.entity_key}|{self.relation_type.value}|{self.target.entity_key}"

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source.to_dict(),
            "relation_type": self.relation_type.value,
            "target": self.target.to_dict(),
            "confidence": self.confidence,
            "source_type": self.source_type,
            "evidence": self.evidence,
            "version": self.version,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class GraphPath:
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]

    def __post_init__(self) -> None:
        if not self.relations or len(self.entities) != len(self.relations) + 1:
            raise ValueError("Graph path must contain one more entity than relation")

    def to_dict(self) -> dict[str, object]:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "relations": [relation.to_dict() for relation in self.relations],
        }


@dataclass(frozen=True)
class GraphMemoryRecall:
    query_entities: tuple[GraphEntity, ...]
    facts: tuple[GraphRelation, ...]
    paths: tuple[GraphPath, ...]
    elapsed_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "query_entities": [entity.to_dict() for entity in self.query_entities],
            "facts": [fact.to_dict() for fact in self.facts],
            "paths": [path.to_dict() for path in self.paths],
            "elapsed_ms": self.elapsed_ms,
        }

