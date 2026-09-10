from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.fleet_vehicle import FleetVehicle
from app.models.vehicle_operation import (
    DomainOutbox,
    MaintenanceBay,
    MaintenanceOrder,
    RescueMission,
    RescueUnit,
    VehicleStatusHistory,
)


def _load_migration_module():
    path = Path(__file__).parents[2] / "alembic" / "versions" / "20260910_15_vehicle_rescue_maintenance.py"
    spec = spec_from_file_location("vehicle_rescue_maintenance", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vehicle_operations_models_register_durable_tables_and_versions():
    assert {
        "fault_code",
        "status_reason",
        "status_changed_at",
        "available_after",
        "maintenance_order_no",
    } <= set(FleetVehicle.__table__.columns)
    assert FleetVehicle.__mapper__.version_id_col is FleetVehicle.__table__.c.version

    assert RescueUnit.__mapper__.version_id_col is RescueUnit.__table__.c.version
    assert RescueMission.__mapper__.version_id_col is RescueMission.__table__.c.version
    assert MaintenanceBay.__mapper__.version_id_col is MaintenanceBay.__table__.c.version
    assert MaintenanceOrder.__mapper__.version_id_col is MaintenanceOrder.__table__.c.version
    assert RescueMission.__table__.c.outbound_edge_ids.type.__class__.__name__ == "JSON"
    assert RescueMission.__table__.c.tow_edge_ids.type.__class__.__name__ == "JSON"
    assert MaintenanceOrder.__table__.c.manual_inspection_required.default.arg is False
    assert next(iter(VehicleStatusHistory.__table__.c.vehicle_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(DomainOutbox.__table__.c.task_id.foreign_keys)).ondelete == "CASCADE"


def test_vehicle_operations_migration_continues_from_current_head():
    module = _load_migration_module()
    assert module.revision == "20260910_15"
    assert module.down_revision == "20260907_14"
