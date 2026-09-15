from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.anomaly_reports.models import (
    AnomalyReportCommand,
    DispatchTaskIdentity,
    PersistedAnomalyReport,
    SourceTaskContext,
)
from app.models.anomaly import Anomaly
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.task import DispatchTask
from app.workspace_reads.sqlalchemy_repository import MY_TASK_STATUS_GROUPS


class SqlAlchemyAnomalyReportRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get_source_task(self, task_id: str) -> SourceTaskContext | None:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                return None
            order = session.get(Order, task.order_id)
            if order is None:
                return None
            vehicle = (
                None
                if order.vehicle_id is None
                else session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == order.vehicle_id))
            )
            driver_id = order.driver_id or (None if vehicle is None else vehicle.assigned_driver_id)
            route_id = order.route_id
            if route_id is None and order.origin_station_id and order.destination_station_id:
                route_id = f"SANDTABLE-{order.origin_station_id}-{order.destination_station_id}"
            return SourceTaskContext(
                task_id=task.task_id,
                task_group=self._task_group(task.status),
                assignee_subject_id=task.assignee_subject_id,
                order_id=order.id,
                driver_id=driver_id,
                vehicle_id=order.vehicle_id,
                route_id=route_id,
                can_report_anomaly=task.anomaly_id is None,
            )

    def get_report_by_key(self, idempotency_key: str) -> PersistedAnomalyReport | None:
        with self._session_factory() as session:
            anomaly = session.scalar(
                select(Anomaly).where(Anomaly.report_idempotency_key == idempotency_key)
            )
            return None if anomaly is None else self._report_record(anomaly)

    def create_report(
        self,
        command: AnomalyReportCommand,
        source: SourceTaskContext,
        principal_subject_id: str,
    ) -> PersistedAnomalyReport:
        with self._session_factory() as session:
            anomaly = Anomaly(
                anomaly_no=f"ANOM-{uuid4().hex[:24].upper()}",
                order_id=source.order_id,
                anomaly_type=command.anomaly_type,
                severity=command.severity,
                description=command.description,
                status="REPORTED",
                reported_by_subject_id=principal_subject_id,
                source_task_id=source.task_id,
                location_text=command.location_text,
                reported_vehicle_status=command.reported_vehicle_status,
                report_idempotency_key=command.idempotency_key,
                incident_node_id=command.incident_node_id,
                affected_edge_id=command.affected_edge_id,
            )
            session.add(anomaly)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(Anomaly).where(
                        Anomaly.report_idempotency_key == command.idempotency_key
                    )
                )
                if existing is None:
                    raise
                return self._report_record(existing)
            session.refresh(anomaly)
            return self._report_record(anomaly)

    def get_dispatch_task_by_key(self, idempotency_key: str) -> DispatchTaskIdentity | None:
        with self._session_factory() as session:
            task = session.scalar(
                select(DispatchTask).where(DispatchTask.idempotency_key == idempotency_key)
            )
            return None if task is None else DispatchTaskIdentity(task.task_id, task.status)

    @staticmethod
    def _task_group(status: str) -> str | None:
        return next(
            (group for group, statuses in MY_TASK_STATUS_GROUPS.items() if status in statuses),
            None,
        )

    @staticmethod
    def _report_record(anomaly: Anomaly) -> PersistedAnomalyReport:
        return PersistedAnomalyReport(
            anomaly_id=anomaly.id,
            anomaly_no=anomaly.anomaly_no,
            order_id=anomaly.order_id,
            source_task_id=anomaly.source_task_id or "",
            anomaly_type=anomaly.anomaly_type,
            description=anomaly.description,
            location_text=anomaly.location_text or "",
            reported_vehicle_status=anomaly.reported_vehicle_status or "",
            severity=anomaly.severity,
            idempotency_key=anomaly.report_idempotency_key or "",
            reported_by_subject_id=anomaly.reported_by_subject_id or "",
            incident_node_id=anomaly.incident_node_id,
            affected_edge_id=anomaly.affected_edge_id,
        )
