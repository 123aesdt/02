from dataclasses import dataclass
from decimal import Decimal

from app.road_network.models import RouteObjective
from app.road_network.protocols import PathFinder, RoadNetworkProvider
from app.vehicle_operations.inspection import SafetyInspectionService
from app.vehicle_operations.models import BreakdownCaseRequest, OperationCaseSnapshot
from app.vehicle_operations.protocols import Clock, VehicleOperationsRepository


class RescueRouteUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BreakdownOrchestrationInput:
    task_id: str
    vehicle_id: str
    replacement_vehicle_id: str | None
    incident_node_id: str
    cargo_type: str
    severity: str
    fault_code: str


class RescueOrchestrationService:
    """Coordinates domain ports; database and routing adapters remain replaceable."""

    def __init__(
        self,
        repository: VehicleOperationsRepository,
        road_network: RoadNetworkProvider,
        path_finder: PathFinder,
        clock: Clock,
        *,
        inspection: SafetyInspectionService | None = None,
        rescue_unit_id: str = "RU-001",
        rescue_node_id: str = "N15",
        maintenance_node_id: str = "N15",
    ) -> None:
        self._repository = repository
        self._road_network = road_network
        self._path_finder = path_finder
        self._clock = clock
        self._inspection = inspection or SafetyInspectionService()
        self._rescue_unit_id = rescue_unit_id
        self._rescue_node_id = rescue_node_id
        self._maintenance_node_id = maintenance_node_id

    def orchestrate(self, command: BreakdownOrchestrationInput) -> OperationCaseSnapshot:
        existing = self._repository.get_case(command.task_id)
        if existing is not None:
            if existing.replacement_vehicle_id is not None and not existing.replacement_edge_ids:
                snapshot = self._road_network.snapshot()
                replacement_origin = self._repository.vehicle_node(existing.replacement_vehicle_id)
                replacement = self._path_finder.find(
                    snapshot,
                    replacement_origin,
                    existing.mission.incident_node_id,
                    RouteObjective.FASTEST,
                    Decimal("4.50"),
                )
                if replacement is None:
                    raise RescueRouteUnavailable("Persisted road topology has no safe replacement pickup route.")
                return self._repository.update_replacement_route(command.task_id, replacement.edge_ids)
            return existing
        snapshot = self._road_network.snapshot()
        outbound = self._path_finder.find(
            snapshot,
            self._rescue_node_id,
            command.incident_node_id,
            RouteObjective.FASTEST,
            Decimal("4.50"),
        )
        tow = self._path_finder.find(
            snapshot,
            command.incident_node_id,
            self._maintenance_node_id,
            RouteObjective.FASTEST,
            Decimal("4.50"),
        )
        if outbound is None or tow is None:
            raise RescueRouteUnavailable("Persisted road topology has no safe rescue/tow route.")
        replacement_edge_ids: tuple[str, ...] = ()
        if command.replacement_vehicle_id is not None:
            replacement_origin = self._repository.vehicle_node(command.replacement_vehicle_id)
            replacement = self._path_finder.find(
                snapshot,
                replacement_origin,
                command.incident_node_id,
                RouteObjective.FASTEST,
                Decimal("4.50"),
            )
            if replacement is None:
                raise RescueRouteUnavailable("Persisted road topology has no safe replacement pickup route.")
            replacement_edge_ids = replacement.edge_ids
        normalized_fault = command.fault_code.strip().upper()
        diagnosis = {
            "ENGINE_COOLING": "发动机冷却系统故障",
            "BRAKE_FAILURE": "制动系统故障，必须人工安全复核",
            "STEERING_FAILURE": "转向系统故障，必须人工安全复核",
        }.get(normalized_fault, "动力系统故障，等待维修诊断")
        return self._repository.create_breakdown_case(
            BreakdownCaseRequest(
                task_id=command.task_id,
                vehicle_id=command.vehicle_id,
                replacement_vehicle_id=command.replacement_vehicle_id,
                rescue_unit_id=self._rescue_unit_id,
                incident_node_id=command.incident_node_id,
                station_node_id=self._maintenance_node_id,
                outbound_edge_ids=outbound.edge_ids,
                tow_edge_ids=tow.edge_ids,
                fault_code=normalized_fault,
                diagnosis=diagnosis,
                repair_minutes=120,
                manual_inspection_required=self._inspection.requires_manual(
                    cargo_type=command.cargo_type,
                    severity=command.severity,
                    fault_code=normalized_fault,
                ),
                occurred_at=self._clock.now(),
                replacement_edge_ids=replacement_edge_ids,
            )
        )
