import pytest
from sqlalchemy import select

from app.anomaly_reports import (
    AnomalyReportCommand,
    AnomalyReportService,
    ReportIdempotencyConflict,
    ReportQueueUnavailable,
    ReportSourceForbidden,
    SourceTaskEnded,
)
from app.anomaly_reports.models import PersistedAnomalyReport, SourceTaskContext
from app.anomaly_reports.sqlalchemy_repository import SqlAlchemyAnomalyReportRepository
from app.models.anomaly import Anomaly
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.order import Order
from app.models.task import DispatchTask
from app.services.dispatch_task_api_service import DispatchTaskApiService
from app.streams.errors import QueueConnectionError


class CapturingQueue:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.messages = []
        self.fail_once = fail_once

    async def publish(self, message) -> None:
        if self.fail_once:
            self.fail_once = False
            raise QueueConnectionError("temporary queue failure")
        self.messages.append(message)


def seed_source_tasks(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add_all(
            [
                DemoEmployeeAccount(
                    employee_id="CF-DEMO-001",
                    display_name="张师傅",
                    role="EMPLOYEE",
                    is_active=True,
                ),
                DemoEmployeeAccount(
                    employee_id="CF-DEMO-006",
                    display_name="陈师傅",
                    role="EMPLOYEE",
                    is_active=True,
                ),
            ]
        )
        owned_order = Order(
            order_no="ORD-OWNED",
            status="IN_TRANSIT",
            driver_id="driver-zhang",
            vehicle_id="vehicle-001",
            route_id="route-xinping",
            origin="青云镇",
            destination="临港镇",
        )
        foreign_order = Order(
            order_no="ORD-FOREIGN",
            status="IN_TRANSIT",
            driver_id="driver-chen",
            vehicle_id="vehicle-006",
            route_id="route-river",
            origin="河西镇",
            destination="临港镇",
        )
        session.add_all([owned_order, foreign_order])
        session.flush()
        session.add_all(
            [
                DispatchTask(
                    task_id="TASK-OWNED",
                    order_id=owned_order.id,
                    status="IN_PROGRESS",
                    idempotency_key="source-owned",
                    assignee_subject_id="CF-DEMO-001",
                ),
                DispatchTask(
                    task_id="TASK-FOREIGN",
                    order_id=foreign_order.id,
                    status="PENDING",
                    idempotency_key="source-foreign",
                    assignee_subject_id="CF-DEMO-006",
                ),
                DispatchTask(
                    task_id="TASK-ENDED",
                    order_id=owned_order.id,
                    status="COMPLETED",
                    idempotency_key="source-ended",
                    assignee_subject_id="CF-DEMO-001",
                ),
            ]
        )
        session.commit()


def command(**changes) -> AnomalyReportCommand:
    values = {
        "source_task_id": "TASK-OWNED",
        "anomaly_type": "ROAD_HAZARD",
        "description": "新平路连续降雨，路面明显湿滑。",
        "location_text": "新平路北段",
        "reported_vehicle_status": "NORMAL",
        "severity": "MEDIUM",
        "idempotency_key": "report-key-001",
    }
    values.update(changes)
    return AnomalyReportCommand(**values)


def build_service(sqlite_factory, queue: CapturingQueue) -> AnomalyReportService:
    return AnomalyReportService(
        SqlAlchemyAnomalyReportRepository(sqlite_factory),
        DispatchTaskApiService(sqlite_factory, queue),
    )


@pytest.mark.asyncio
async def test_submit_derives_dispatch_context_and_persists_report(sqlite_factory) -> None:
    seed_source_tasks(sqlite_factory)
    queue = CapturingQueue()

    result = await build_service(sqlite_factory, queue).submit(
        command(), principal_subject_id="CF-DEMO-001"
    )

    with sqlite_factory() as session:
        anomaly = session.scalar(select(Anomaly).where(Anomaly.id == result.anomaly_id))
        task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == result.task_id))
    assert anomaly is not None
    assert task is not None
    assert anomaly.order_id == task.order_id
    assert anomaly.reported_by_subject_id == "CF-DEMO-001"
    assert task.anomaly_id == anomaly.id
    assert task.assignee_subject_id == "CF-DEMO-001"
    assert queue.messages[0].payload == {
        "driver_id": "driver-zhang",
        "vehicle_id": "vehicle-001",
        "route_id": "route-xinping",
        "anomaly_type": "ROAD_HAZARD",
        "anomaly_description": "新平路连续降雨，路面明显湿滑。",
        "vehicle_status": "NORMAL",
    }


@pytest.mark.asyncio
async def test_submit_rejects_foreign_and_ended_source_tasks(sqlite_factory) -> None:
    seed_source_tasks(sqlite_factory)
    service = build_service(sqlite_factory, CapturingQueue())

    with pytest.raises(ReportSourceForbidden):
        await service.submit(
            command(source_task_id="TASK-FOREIGN"),
            principal_subject_id="CF-DEMO-001",
        )
    with pytest.raises(SourceTaskEnded):
        await service.submit(
            command(source_task_id="TASK-ENDED"),
            principal_subject_id="CF-DEMO-001",
        )


@pytest.mark.asyncio
async def test_submit_replays_one_report_and_rejects_changed_content(sqlite_factory) -> None:
    seed_source_tasks(sqlite_factory)
    queue = CapturingQueue()
    service = build_service(sqlite_factory, queue)

    first = await service.submit(command(), principal_subject_id="CF-DEMO-001")
    replay = await service.submit(command(), principal_subject_id="CF-DEMO-001")

    assert replay.anomaly_id == first.anomaly_id
    assert replay.task_id == first.task_id
    assert replay.duplicate is True
    assert len(queue.messages) == 1
    with pytest.raises(ReportIdempotencyConflict):
        await service.submit(
            command(description="同一个键却换成了不同的问题内容。"),
            principal_subject_id="CF-DEMO-001",
        )


@pytest.mark.asyncio
async def test_submit_rechecks_concurrent_idempotency_winner() -> None:
    source = SourceTaskContext(
        task_id="TASK-OWNED",
        task_group="ACTIVE",
        assignee_subject_id="CF-DEMO-001",
        order_id=1,
        driver_id="driver-zhang",
        vehicle_id="vehicle-001",
        route_id="route-xinping",
    )
    winner = PersistedAnomalyReport(
        anomaly_id=1,
        anomaly_no="ANOM-WINNER",
        order_id=1,
        source_task_id="TASK-OWNED",
        anomaly_type="ROAD_HAZARD",
        description="另一个并发请求使用了相同键。",
        location_text="新平路北段",
        reported_vehicle_status="NORMAL",
        severity="MEDIUM",
        idempotency_key="report-key-001",
        reported_by_subject_id="CF-DEMO-001",
    )

    class RacingRepository:
        def get_source_task(self, task_id):
            return source

        def get_report_by_key(self, idempotency_key):
            return None

        def create_report(self, submitted, task_context, principal_subject_id):
            return winner

        def get_dispatch_task_by_key(self, idempotency_key):
            raise AssertionError("conflicting report must not dispatch")

    class RejectingDispatchService:
        async def submit(self, request, *, assignee_subject_id):
            raise AssertionError("conflicting report must not dispatch")

    service = AnomalyReportService(RacingRepository(), RejectingDispatchService())

    with pytest.raises(ReportIdempotencyConflict):
        await service.submit(command(), principal_subject_id="CF-DEMO-001")

@pytest.mark.asyncio
async def test_queue_failure_retries_same_anomaly_and_dispatch_task(sqlite_factory) -> None:
    seed_source_tasks(sqlite_factory)
    queue = CapturingQueue(fail_once=True)
    service = build_service(sqlite_factory, queue)

    with pytest.raises(ReportQueueUnavailable) as failure:
        await service.submit(command(), principal_subject_id="CF-DEMO-001")

    retry = await service.submit(command(), principal_subject_id="CF-DEMO-001")

    assert retry.anomaly_id == failure.value.anomaly_id
    assert retry.task_id == failure.value.task_id
    assert retry.status == "PENDING"
    assert len(queue.messages) == 1
