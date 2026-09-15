from app.models.anomaly import Anomaly
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask
from app.sandtable.sqlalchemy_repository import seed_new_county_sandtable
from app.streams.models import DispatchTaskMessage
from app.vehicle_operations.dispatch_bridge import SqlAlchemyVehicleBreakdownHandler


class _Orchestrator:
    def __init__(self) -> None:
        self.command = None

    def orchestrate(self, command):
        self.command = command


def test_dispatch_bridge_builds_breakdown_command_from_durable_dispatch(sqlite_factory):
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        order = session.query(Order).filter_by(order_no="DEMO-ORDER-001").one()
        anomaly = Anomaly(
            anomaly_no="ANOM-BRIDGE-001",
            order_id=order.id,
            anomaly_type="VEHICLE_BREAKDOWN",
            severity="HIGH",
            description="发动机冷却系统温度异常，车辆已停驶。",
            incident_node_id="N04",
            status="OPEN",
        )
        session.add(anomaly)
        session.flush()
        task = DispatchTask(
            task_id="TASK-BRIDGE-001",
            order_id=order.id,
            anomaly_id=anomaly.id,
            status="APPROVED",
            idempotency_key="bridge-001",
        )
        session.add(task)
        session.flush()
        session.add(
            Dispatch(
                dispatch_no="DSP-BRIDGE-001",
                order_id=order.id,
                task_id=task.id,
                original_vehicle_id="V-001",
                target_vehicle_id="V-005",
                transfer_node_id="N04",
                status="REROUTED",
            )
        )
        session.commit()

    orchestrator = _Orchestrator()
    handler = SqlAlchemyVehicleBreakdownHandler(sqlite_factory, orchestrator)
    handler.handle_approved_breakdown(
        DispatchTaskMessage(
            schema_version="1",
            task_id="TASK-BRIDGE-001",
            order_id=order.id,
            anomaly_id=anomaly.id,
            idempotency_key="bridge-001",
            created_at="2026-09-10T10:42:00+08:00",
            payload={
                "driver_id": "D-001",
                "vehicle_id": "V-001",
                "route_id": "ROUTE-01",
                "anomaly_type": "VEHICLE_BREAKDOWN",
                "anomaly_description": "发动机冷却系统温度异常，车辆已停驶。",
                "vehicle_status": "BROKEN",
            },
        )
    )

    assert orchestrator.command.task_id == "TASK-BRIDGE-001"
    assert orchestrator.command.vehicle_id == "V-001"
    assert orchestrator.command.replacement_vehicle_id == "V-005"
    assert orchestrator.command.incident_node_id == "N04"
    assert orchestrator.command.fault_code == "ENGINE_COOLING"
