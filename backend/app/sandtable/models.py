from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SandtableTaskContext:
    order_id: int
    order_no: str
    cargo_weight_kg: Decimal
    cargo_type: str
    origin_node_id: str
    destination_node_id: str
    current_vehicle_id: str
    current_driver_id: str | None
    incident_node_id: str | None
    affected_edge_ids: tuple[str, ...]
    road_network_version: int
