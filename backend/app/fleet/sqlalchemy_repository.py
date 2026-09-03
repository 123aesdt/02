from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import FleetDriverSnapshot, FleetVehicleSnapshot
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle

_QUANTUM = Decimal("0.01")


def _decimal(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


class SqlAlchemyFleetRepository:
    """Maps ORM rows to detached immutable fleet snapshots."""

    def __init__(self, session: Session | object) -> None:
        self._session = session

    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]:
        owns_session = callable(self._session)
        session = self._session() if owns_session else self._session
        try:
            drivers = {
                driver.driver_id: FleetDriverSnapshot(driver.driver_id, driver.name, driver.license_class, driver.status, driver.current_node_id)
                for driver in session.scalars(select(FleetDriver))
            }
            return tuple(
                FleetVehicleSnapshot(
                    vehicle.vehicle_id,
                    vehicle.plate_no,
                    vehicle.vehicle_type,
                    _decimal(vehicle.max_load_kg),
                    _decimal(vehicle.current_load_kg),
                    vehicle.cargo_capability,
                    _decimal(vehicle.gross_weight_tons),
                    vehicle.status,
                    vehicle.current_node_id,
                    drivers.get(vehicle.assigned_driver_id),
                )
                for vehicle in session.scalars(select(FleetVehicle).order_by(FleetVehicle.vehicle_id))
            )
        finally:
            if owns_session:
                session.close()
