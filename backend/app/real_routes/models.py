from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GeoPoint:
    node_id: str | None
    longitude: Decimal
    latitude: Decimal


@dataclass(frozen=True, slots=True)
class DrivingRouteResult:
    distance_meters: int
    duration_seconds: int
    polyline: tuple[GeoPoint, ...]


@dataclass(frozen=True, slots=True)
class RealRoadRoute:
    provider: str
    source: str
    status: str
    coordinate_system: str
    mapping_version: str
    distance_meters: int | None
    duration_seconds: int | None
    waypoints: tuple[GeoPoint, ...]
    polyline: tuple[GeoPoint, ...]
    fallback_reason: str | None
