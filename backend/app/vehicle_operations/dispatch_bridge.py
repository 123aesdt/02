from sqlalchemy import select

from app.models.anomaly import Anomaly
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask
from app.streams.models import DispatchTaskMessage
from app.vehicle_operations.service import BreakdownOrchestrationInput


class VehicleBreakdownContextMissing(LookupError):
    pass


class SqlAlchemyVehicleBreakdownHandler:
    """Maps an approved dispatch to the narrow vehicle-operations application port."""

    def __init__(self, session_factory, orchestrator) -> None:
        self._session_factory = session_factory
        self._orchestrator = orchestrator

    def handle_approved_breakdown(self, message: DispatchTaskMessage) -> None:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == message.task_id))
            if task is None:
                raise VehicleBreakdownContextMissing(message.task_id)
            order = session.get(Order, task.order_id)
            anomaly = session.get(Anomaly, task.anomaly_id) if task.anomaly_id is not None else None
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id == task.id))
            if order is None:
                raise VehicleBreakdownContextMissing(f"order:{task.order_id}")

            original_vehicle_id = dispatch.original_vehicle_id if dispatch is not None and dispatch.original_vehicle_id else str(message.payload["vehicle_id"])
            replacement_vehicle_id = dispatch.target_vehicle_id if dispatch is not None else None
            if replacement_vehicle_id == original_vehicle_id:
                replacement_vehicle_id = None
            incident_node_id = (
                anomaly.incident_node_id
                if anomaly is not None and anomaly.incident_node_id
                else dispatch.transfer_node_id
                if dispatch is not None and dispatch.transfer_node_id
                else "N04"
            )
            description = anomaly.description if anomaly is not None else str(message.payload.get("anomaly_description", ""))
            severity = anomaly.severity if anomaly is not None else "HIGH"
            cargo_type = order.cargo_type or "GENERAL"

        self._orchestrator.orchestrate(
            BreakdownOrchestrationInput(
                task_id=message.task_id,
                vehicle_id=original_vehicle_id,
                replacement_vehicle_id=replacement_vehicle_id,
                incident_node_id=incident_node_id,
                cargo_type=cargo_type,
                severity=severity,
                fault_code=self._fault_code(description),
            )
        )

    @staticmethod
    def _fault_code(description: str) -> str:
        normalized = description.upper()
        if "制动" in description or "刹车" in description or "BRAKE" in normalized:
            return "BRAKE_FAILURE"
        if "转向" in description or "方向" in description or "STEERING" in normalized:
            return "STEERING_FAILURE"
        if "冷却" in description or "水温" in description or "COOLING" in normalized:
            return "ENGINE_COOLING"
        return "POWERTRAIN_FAILURE"
