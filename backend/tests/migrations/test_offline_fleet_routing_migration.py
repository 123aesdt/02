from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.dispatch import Dispatch
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge


def test_offline_fleet_models_expose_required_fields() -> None:
    assert {"cargo_weight_kg", "cargo_type", "origin_station_id", "destination_station_id"} <= set(Order.__table__.columns.keys())
    assert {"original_vehicle_id", "target_vehicle_id", "transfer_node_id"} <= set(Dispatch.__table__.columns.keys())
    assert FleetVehicle.__mapper__.version_id_col is FleetVehicle.__table__.c.version
    assert RoadEdge.__mapper__.version_id_col is RoadEdge.__table__.c.version


def test_offline_fleet_migration_continues_from_current_head() -> None:
    path = Path(__file__).parents[2] / "alembic" / "versions" / "20260902_13_offline_fleet_routing.py"
    spec = spec_from_file_location("offline_fleet_routing", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "20260902_13"
    assert module.down_revision == "20260901_12"
