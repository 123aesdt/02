from sqlalchemy import select

from app.models.vehicle_operation import MaintenanceBay, RescueUnit
from app.vehicle_operations.seed import seed_vehicle_operation_resources


def test_vehicle_operation_resources_are_seeded_idempotently(sqlite_factory):
    with sqlite_factory() as session:
        seed_vehicle_operation_resources(session)
        seed_vehicle_operation_resources(session)
        session.commit()
        units = list(session.scalars(select(RescueUnit)))
        bays = list(session.scalars(select(MaintenanceBay)))

    assert [(unit.unit_id, unit.current_node_id, unit.status) for unit in units] == [("RU-001", "N15", "AVAILABLE")]
    assert [(bay.bay_code, bay.station_id, bay.status) for bay in bays] == [("A-02", "ST-007", "AVAILABLE")]
