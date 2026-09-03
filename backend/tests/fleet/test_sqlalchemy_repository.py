from decimal import Decimal

from app.fleet.sqlalchemy_repository import SqlAlchemyFleetRepository
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.road import RoadNode


def test_repository_returns_immutable_id_sorted_snapshots_after_session_scope(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add_all(
            [
                RoadNode(node_id="N01", name="N01", x_km=Decimal("0"), y_km=Decimal("0"), node_type="JUNCTION"),
                FleetDriver(driver_id="D-002", name="driver", license_class="C1", status="ON_DUTY", current_node_id="N01"),
                FleetVehicle(
                    vehicle_id="V-002", plate_no="V-002", vehicle_type="VAN", max_load_kg=Decimal("1000"), current_load_kg=Decimal("250"),
                    cargo_capability="GENERAL", gross_weight_tons=Decimal("2.2"), status="AVAILABLE", current_node_id="N01", assigned_driver_id="D-002",
                ),
            ]
        )
        session.commit()
        snapshots = SqlAlchemyFleetRepository(session).list_candidates("V-001")
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert (snapshot.vehicle_id, snapshot.remaining_load_kg, snapshot.driver.driver_id if snapshot.driver else None) == (
        "V-002",
        Decimal("750.00"),
        "D-002",
    )
    assert snapshot.max_load_kg == Decimal("1000.00")
