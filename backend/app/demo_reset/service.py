from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.road import RoadEdge
from app.models.vehicle_operation import MaintenanceBay, MaintenanceOrder, RescueMission, RescueUnit


class DemoScenarioNotFound(LookupError):
    pass


class DemoScenarioForbidden(PermissionError):
    pass


class DemoScenarioStateIncomplete(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DemoScenarioResetResult:
    scenario_id: str
    status: str = "READY"
    message: str = "演示场景已恢复，可以再次提交。"


class DemoScenarioResetService:
    _ALLOWED_SUBJECTS = {
        "VEHICLE_BREAKDOWN_N04": frozenset({"CF-DEMO-001"}),
        "ROAD_BLOCKED_E04": frozenset({"CF-DEMO-001", "CF-DEMO-006"}),
    }
    _ACTIVE_RESCUE_STATUSES = ("CREATED", "DISPATCHED", "ARRIVED", "LOADED")
    _ACTIVE_MAINTENANCE_STATUSES = (
        "SCHEDULED", "WAITING_BAY", "DIAGNOSING", "REPAIRING", "QA_PENDING"
    )

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def reset(self, scenario_id: str, *, principal_subject_id: str) -> DemoScenarioResetResult:
        allowed_subjects = self._ALLOWED_SUBJECTS.get(scenario_id)
        if allowed_subjects is None:
            raise DemoScenarioNotFound(scenario_id)
        if principal_subject_id not in allowed_subjects:
            raise DemoScenarioForbidden(principal_subject_id)

        with self._session_factory() as session, session.begin():
            self._reset_roads(session)
            if scenario_id == "VEHICLE_BREAKDOWN_N04":
                self._reset_vehicle_breakdown(session)
        return DemoScenarioResetResult(scenario_id=scenario_id)

    def _reset_roads(self, session: Session) -> None:
        roads = {
            road.edge_id: road
            for road in session.scalars(
                select(RoadEdge)
                .where(RoadEdge.edge_id.in_(("E04", "E10")))
                .with_for_update()
            )
        }
        self._require_rows(roads, {"E04", "E10"}, "road edges")
        for road in roads.values():
            road.status = "OPEN"
            road.congestion_factor = Decimal("1.00")

    def _reset_vehicle_breakdown(self, session: Session) -> None:
        vehicle_specs = {
            "V-002": ("IN_TRANSIT", "N01", "D-002"),
            "V-003": ("AVAILABLE", "N15", "D-011"),
            "V-011": ("AVAILABLE", "N14", "D-012"),
        }
        vehicles = {
            vehicle.vehicle_id: vehicle
            for vehicle in session.scalars(
                select(FleetVehicle)
                .where(FleetVehicle.vehicle_id.in_(tuple(vehicle_specs)))
                .with_for_update()
            )
        }
        self._require_rows(vehicles, set(vehicle_specs), "fleet vehicles")
        for vehicle_id, (status, node_id, driver_id) in vehicle_specs.items():
            vehicle = vehicles[vehicle_id]
            vehicle.status = status
            vehicle.current_node_id = node_id
            vehicle.assigned_driver_id = driver_id
            vehicle.fault_code = None
            vehicle.status_reason = None
            vehicle.status_changed_at = None
            vehicle.available_after = None
            vehicle.maintenance_order_no = None

        driver_specs = {
            "D-002": ("V-002", "N01"),
            "D-011": ("V-003", "N15"),
            "D-012": ("V-011", "N14"),
        }
        drivers = {
            driver.driver_id: driver
            for driver in session.scalars(
                select(FleetDriver)
                .where(FleetDriver.driver_id.in_(tuple(driver_specs)))
                .with_for_update()
            )
        }
        self._require_rows(drivers, set(driver_specs), "fleet drivers")
        for driver_id, (vehicle_id, node_id) in driver_specs.items():
            driver = drivers[driver_id]
            driver.status = "ON_DUTY"
            driver.current_vehicle_id = vehicle_id
            driver.current_node_id = node_id

        for mission in session.scalars(
            select(RescueMission)
            .where(RescueMission.status.in_(self._ACTIVE_RESCUE_STATUSES))
            .with_for_update()
        ):
            mission.status = "CANCELLED"
            mission.next_transition_at = None
            mission.failure_reason = "DEMO_RESET"
        for order in session.scalars(
            select(MaintenanceOrder)
            .where(MaintenanceOrder.status.in_(self._ACTIVE_MAINTENANCE_STATUSES))
            .with_for_update()
        ):
            order.status = "CANCELLED"
            order.next_transition_at = None
            order.available_after = None

        for unit in session.scalars(select(RescueUnit).with_for_update()):
            unit.status = "AVAILABLE"
        for bay in session.scalars(select(MaintenanceBay).with_for_update()):
            bay.status = "AVAILABLE"
            bay.current_order_no = None

    @staticmethod
    def _require_rows(rows: dict[str, object], expected: set[str], label: str) -> None:
        missing = expected.difference(rows)
        if missing:
            raise DemoScenarioStateIncomplete(
                f"Missing {label}: {', '.join(sorted(missing))}"
            )
