from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InvalidStateTransition(ValueError):
    pass


class VehicleOperationalStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    IN_TRANSIT = "IN_TRANSIT"
    DISPATCHING = "DISPATCHING"
    BROKEN = "BROKEN"
    WAITING_RESCUE = "WAITING_RESCUE"
    IN_RESCUE = "IN_RESCUE"
    MAINTENANCE = "MAINTENANCE"
    QA_PENDING = "QA_PENDING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class RescueStatus(StrEnum):
    CREATED = "CREATED"
    DISPATCHED = "DISPATCHED"
    ARRIVED = "ARRIVED"
    LOADED = "LOADED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MaintenanceStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    WAITING_BAY = "WAITING_BAY"
    DIAGNOSING = "DIAGNOSING"
    REPAIRING = "REPAIRING"
    QA_PENDING = "QA_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_VEHICLE_TRANSITIONS = {
    VehicleOperationalStatus.AVAILABLE: frozenset({VehicleOperationalStatus.RESERVED, VehicleOperationalStatus.DISPATCHING}),
    VehicleOperationalStatus.RESERVED: frozenset({VehicleOperationalStatus.DISPATCHING}),
    VehicleOperationalStatus.DISPATCHING: frozenset({VehicleOperationalStatus.IN_TRANSIT}),
    VehicleOperationalStatus.IN_TRANSIT: frozenset({VehicleOperationalStatus.BROKEN}),
    VehicleOperationalStatus.BROKEN: frozenset({VehicleOperationalStatus.WAITING_RESCUE}),
    VehicleOperationalStatus.WAITING_RESCUE: frozenset({VehicleOperationalStatus.IN_RESCUE}),
    VehicleOperationalStatus.IN_RESCUE: frozenset({VehicleOperationalStatus.MAINTENANCE}),
    VehicleOperationalStatus.MAINTENANCE: frozenset({VehicleOperationalStatus.QA_PENDING}),
    VehicleOperationalStatus.QA_PENDING: frozenset({VehicleOperationalStatus.AVAILABLE, VehicleOperationalStatus.OUT_OF_SERVICE}),
}

_RESCUE_TRANSITIONS = {
    RescueStatus.CREATED: frozenset({RescueStatus.DISPATCHED, RescueStatus.CANCELLED}),
    RescueStatus.DISPATCHED: frozenset({RescueStatus.ARRIVED, RescueStatus.FAILED, RescueStatus.CANCELLED}),
    RescueStatus.ARRIVED: frozenset({RescueStatus.LOADED, RescueStatus.FAILED, RescueStatus.CANCELLED}),
    RescueStatus.LOADED: frozenset({RescueStatus.DELIVERED, RescueStatus.FAILED, RescueStatus.CANCELLED}),
}

_MAINTENANCE_TRANSITIONS = {
    MaintenanceStatus.SCHEDULED: frozenset({MaintenanceStatus.WAITING_BAY, MaintenanceStatus.CANCELLED}),
    MaintenanceStatus.WAITING_BAY: frozenset({MaintenanceStatus.DIAGNOSING, MaintenanceStatus.CANCELLED}),
    MaintenanceStatus.DIAGNOSING: frozenset({MaintenanceStatus.REPAIRING, MaintenanceStatus.FAILED}),
    MaintenanceStatus.REPAIRING: frozenset({MaintenanceStatus.QA_PENDING, MaintenanceStatus.FAILED}),
    MaintenanceStatus.QA_PENDING: frozenset({MaintenanceStatus.COMPLETED, MaintenanceStatus.FAILED}),
}


def _require_transition(current: StrEnum, target: StrEnum, transitions: dict[StrEnum, frozenset[StrEnum]]) -> None:
    if target not in transitions.get(current, frozenset()):
        raise InvalidStateTransition(f"Invalid transition: {current.value} -> {target.value}")


def require_vehicle_transition(current: VehicleOperationalStatus, target: VehicleOperationalStatus) -> None:
    _require_transition(current, target, _VEHICLE_TRANSITIONS)


def require_rescue_transition(current: RescueStatus, target: RescueStatus) -> None:
    _require_transition(current, target, _RESCUE_TRANSITIONS)


def require_maintenance_transition(current: MaintenanceStatus, target: MaintenanceStatus) -> None:
    _require_transition(current, target, _MAINTENANCE_TRANSITIONS)


@dataclass(frozen=True, slots=True)
class RescueMissionSnapshot:
    mission_no: str
    task_id: str
    vehicle_id: str
    rescue_unit_id: str
    status: RescueStatus
    incident_node_id: str
    station_node_id: str
    outbound_edge_ids: tuple[str, ...]
    tow_edge_ids: tuple[str, ...]
    next_transition_at: datetime | None
    version: int

    @property
    def progress_percent(self) -> int:
        return {
            RescueStatus.CREATED: 0,
            RescueStatus.DISPATCHED: 25,
            RescueStatus.ARRIVED: 50,
            RescueStatus.LOADED: 75,
            RescueStatus.DELIVERED: 100,
            RescueStatus.FAILED: 100,
            RescueStatus.CANCELLED: 100,
        }[self.status]


@dataclass(frozen=True, slots=True)
class MaintenanceOrderSnapshot:
    order_no: str
    task_id: str
    vehicle_id: str
    bay_code: str | None
    status: MaintenanceStatus
    fault_code: str
    diagnosis: str | None
    repair_minutes: int
    manual_inspection_required: bool
    next_transition_at: datetime | None
    available_after: datetime | None
    version: int
    inspection_result: str | None = None

    @property
    def progress_percent(self) -> int:
        return {
            MaintenanceStatus.SCHEDULED: 0,
            MaintenanceStatus.WAITING_BAY: 15,
            MaintenanceStatus.DIAGNOSING: 35,
            MaintenanceStatus.REPAIRING: 68,
            MaintenanceStatus.QA_PENDING: 90,
            MaintenanceStatus.COMPLETED: 100,
            MaintenanceStatus.FAILED: 100,
            MaintenanceStatus.CANCELLED: 100,
        }[self.status]

    def seconds_remaining(self, now: datetime) -> int | None:
        if self.available_after is None:
            return None
        deadline = self.available_after
        if deadline.tzinfo is None and now.tzinfo is not None:
            deadline = deadline.replace(tzinfo=now.tzinfo)
        elif deadline.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=deadline.tzinfo)
        return max(0, int((deadline - now).total_seconds()))


@dataclass(frozen=True, slots=True)
class BreakdownCaseRequest:
    task_id: str
    vehicle_id: str
    replacement_vehicle_id: str | None
    rescue_unit_id: str
    incident_node_id: str
    station_node_id: str
    outbound_edge_ids: tuple[str, ...]
    tow_edge_ids: tuple[str, ...]
    fault_code: str
    diagnosis: str
    repair_minutes: int
    manual_inspection_required: bool
    occurred_at: datetime
    replacement_edge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationCaseSnapshot:
    task_id: str
    vehicle_id: str
    vehicle_status: str
    replacement_vehicle_id: str | None
    replacement_vehicle_status: str | None
    mission: RescueMissionSnapshot
    maintenance: MaintenanceOrderSnapshot
    replacement_edge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InspectionDecision:
    order_no: str
    passed: bool
    decided_at: datetime
