from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fleet.models import FleetDriverSnapshot, FleetVehicleSnapshot
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle

_QUANTUM = Decimal("0.01")


def _decimal(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _driver_snapshot(driver: FleetDriver | None) -> FleetDriverSnapshot | None:
    if driver is None:
        return None
    return FleetDriverSnapshot(driver.driver_id, driver.name, driver.license_class, driver.status, driver.current_node_id)


def _vehicle_snapshot(vehicle: FleetVehicle, driver: FleetDriver | None) -> FleetVehicleSnapshot:
    return FleetVehicleSnapshot(
        vehicle.vehicle_id,
        vehicle.plate_no,
        vehicle.vehicle_type,
        _decimal(vehicle.max_load_kg),
        _decimal(vehicle.current_load_kg),
        vehicle.cargo_capability,
        _decimal(vehicle.gross_weight_tons),
        vehicle.status,
        vehicle.current_node_id,
        _driver_snapshot(driver),
    )


class SqlAlchemyFleetRepository:
    """Maps ORM rows to detached immutable fleet snapshots."""

    def __init__(self, session: Session | object) -> None:
        self._session = session

    def get_vehicle(self, vehicle_id: str) -> FleetVehicleSnapshot | None:
        owns_session = callable(self._session)
        session = self._session() if owns_session else self._session
        try:
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == vehicle_id))
            if vehicle is None:
                return None
            driver = (
                session.scalar(select(FleetDriver).where(FleetDriver.driver_id == vehicle.assigned_driver_id))
                if vehicle.assigned_driver_id is not None
                else None
            )
            return _vehicle_snapshot(vehicle, driver)
        finally:
            if owns_session:
                session.close()

    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]:
        owns_session = callable(self._session)
        session = self._session() if owns_session else self._session
        try:
            drivers = {driver.driver_id: driver for driver in session.scalars(select(FleetDriver))}
            return tuple(
                _vehicle_snapshot(vehicle, drivers.get(vehicle.assigned_driver_id))
                for vehicle in session.scalars(select(FleetVehicle).order_by(FleetVehicle.vehicle_id))
            )
        finally:
            if owns_session:
                session.close()
