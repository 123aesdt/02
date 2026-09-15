import re
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.errors import OptimisticLockConflict
from app.models.fleet_vehicle import FleetVehicle
from app.models.vehicle_operation import (
    DomainOutbox,
    MaintenanceBay,
    MaintenanceOrder,
    RescueMission,
    RescueUnit,
    VehicleStatusHistory,
)
from app.vehicle_operations.models import (
    BreakdownCaseRequest,
    InvalidStateTransition,
    MaintenanceOrderSnapshot,
    MaintenanceStatus,
    OperationCaseSnapshot,
    RescueMissionSnapshot,
    RescueStatus,
    VehicleOperationalStatus,
    require_maintenance_transition,
    require_rescue_transition,
    require_vehicle_transition,
)


class VehicleOperationNotFound(LookupError):
    pass


class VehicleOperationsConflict(RuntimeError):
    pass


class SqlAlchemyVehicleOperationsRepository:
    """Transactional MySQL source of truth for the physical vehicle lifecycle."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def vehicle_node(self, vehicle_id: str) -> str:
        with self._session_factory() as session:
            node_id = session.scalar(select(FleetVehicle.current_node_id).where(FleetVehicle.vehicle_id == vehicle_id))
        if node_id is None:
            raise VehicleOperationNotFound(vehicle_id)
        return node_id

    def update_replacement_route(self, task_id: str, edge_ids: tuple[str, ...]) -> OperationCaseSnapshot:
        with self._session_factory() as session, session.begin():
            event = session.scalar(
                select(DomainOutbox)
                .where(
                    DomainOutbox.task_id == task_id,
                    DomainOutbox.event_type == "REPLACEMENT_DISPATCHED",
                )
                .order_by(DomainOutbox.id)
                .with_for_update()
            )
            mission = session.scalar(
                select(RescueMission)
                .where(RescueMission.task_id == task_id)
                .with_for_update()
            )
            if event is None or mission is None:
                raise VehicleOperationNotFound(task_id)
            payload = dict(event.payload_json)
            payload["edge_ids"] = list(edge_ids)
            event.payload_json = payload
            session.flush()
            return self._case(session, mission)

    def create_breakdown_case(self, request: BreakdownCaseRequest) -> OperationCaseSnapshot:
        try:
            with self._session_factory() as session, session.begin():
                existing = session.scalar(select(RescueMission).where(RescueMission.task_id == request.task_id))
                if existing is not None:
                    return self._case(session, existing)

                vehicle = self._vehicle_for_update(session, request.vehicle_id)
                rescue_unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == request.rescue_unit_id).with_for_update())
                if rescue_unit is None or rescue_unit.status != "AVAILABLE":
                    raise VehicleOperationsConflict("No available rescue unit for this breakdown.")
                bay = session.scalar(
                    select(MaintenanceBay).where(MaintenanceBay.status == "AVAILABLE").order_by(MaintenanceBay.bay_code).with_for_update(skip_locked=True)
                )
                if bay is None:
                    raise VehicleOperationsConflict("No maintenance bay is available.")

                self._transition_vehicle(session, vehicle, VehicleOperationalStatus.BROKEN, "员工上报车辆故障并安全停车", request.task_id, request.occurred_at)
                self._transition_vehicle(
                    session, vehicle, VehicleOperationalStatus.WAITING_RESCUE, "救援与拖车任务已创建", request.task_id, request.occurred_at
                )
                vehicle.fault_code = request.fault_code

                replacement = None
                if request.replacement_vehicle_id is not None:
                    replacement = self._vehicle_for_update(session, request.replacement_vehicle_id)
                    self._transition_vehicle(
                        session, replacement, VehicleOperationalStatus.DISPATCHING, "接替故障车辆配送任务", request.task_id, request.occurred_at
                    )
                    self._transition_vehicle(
                        session, replacement, VehicleOperationalStatus.IN_TRANSIT, "货物责任已转移并继续配送", request.task_id, request.occurred_at
                    )

                suffix = self._suffix(request.task_id)
                mission_no = f"JY-{request.occurred_at:%Y%m%d}-{suffix}"
                order_no = f"WX-{request.occurred_at:%Y%m%d}-{suffix}"
                mission = RescueMission(
                    mission_no=mission_no,
                    task_id=request.task_id,
                    vehicle_id=request.vehicle_id,
                    rescue_unit_id=request.rescue_unit_id,
                    status=RescueStatus.DISPATCHED.value,
                    incident_node_id=request.incident_node_id,
                    station_node_id=request.station_node_id,
                    outbound_edge_ids=list(request.outbound_edge_ids),
                    tow_edge_ids=list(request.tow_edge_ids),
                    next_transition_at=request.occurred_at + timedelta(seconds=8),
                    attempt_count=0,
                )
                maintenance = MaintenanceOrder(
                    order_no=order_no,
                    task_id=request.task_id,
                    vehicle_id=request.vehicle_id,
                    bay_code=bay.bay_code,
                    status=MaintenanceStatus.SCHEDULED.value,
                    fault_code=request.fault_code,
                    diagnosis=request.diagnosis,
                    repair_minutes=request.repair_minutes,
                    manual_inspection_required=request.manual_inspection_required,
                    next_transition_at=None,
                    available_after=None,
                )
                session.add_all((mission, maintenance))
                rescue_unit.status = "DISPATCHED"
                bay.status = "RESERVED"
                bay.current_order_no = order_no
                vehicle.maintenance_order_no = order_no
                vehicle.available_after = maintenance.available_after

                replacement_id = replacement.vehicle_id if replacement is not None else None
                self._event(session, request.task_id, "vehicle", request.vehicle_id, "VEHICLE_STOPPED", {"vehicle_id": request.vehicle_id})
                if replacement_id:
                    self._event(
                        session,
                        request.task_id,
                        "vehicle",
                        replacement_id,
                        "REPLACEMENT_DISPATCHED",
                        {"vehicle_id": replacement_id, "edge_ids": list(request.replacement_edge_ids)},
                    )
                self._event(session, request.task_id, "rescue", mission_no, "RESCUE_DISPATCHED", {"mission_no": mission_no})
                self._event(session, request.task_id, "maintenance", order_no, "MAINTENANCE_SCHEDULED", {"order_no": order_no})
                session.flush()
                return self._case(session, mission)
        except StaleDataError as error:
            raise OptimisticLockConflict(-1) from error

    def get_case(self, task_id: str) -> OperationCaseSnapshot | None:
        with self._session_factory() as session:
            mission = session.scalar(select(RescueMission).where(RescueMission.task_id == task_id))
            return None if mission is None else self._case(session, mission)

    def advance_one_due_rescue(self, now: datetime) -> OperationCaseSnapshot | None:
        active = (RescueStatus.DISPATCHED.value, RescueStatus.ARRIVED.value, RescueStatus.LOADED.value)
        try:
            with self._session_factory() as session, session.begin():
                mission = session.scalar(
                    select(RescueMission)
                    .where(RescueMission.status.in_(active), RescueMission.next_transition_at <= now)
                    .order_by(RescueMission.next_transition_at, RescueMission.id)
                    .with_for_update(skip_locked=True)
                )
                if mission is None:
                    return None
                current = RescueStatus(mission.status)
                target = {
                    RescueStatus.DISPATCHED: RescueStatus.ARRIVED,
                    RescueStatus.ARRIVED: RescueStatus.LOADED,
                    RescueStatus.LOADED: RescueStatus.DELIVERED,
                }[current]
                require_rescue_transition(current, target)
                mission.status = target.value
                mission.attempt_count += 1
                delays = {RescueStatus.ARRIVED: 6, RescueStatus.LOADED: 4}
                mission.next_transition_at = now + timedelta(seconds=delays[target]) if target in delays else None
                event_type = {
                    RescueStatus.ARRIVED: "RESCUE_ARRIVED",
                    RescueStatus.LOADED: "VEHICLE_LOADED",
                    RescueStatus.DELIVERED: "TOW_DELIVERED",
                }[target]
                self._event(session, mission.task_id, "rescue", mission.mission_no, event_type, {"status": target.value})
                if target is RescueStatus.LOADED:
                    vehicle = self._vehicle_for_update(session, mission.vehicle_id)
                    self._transition_vehicle(session, vehicle, VehicleOperationalStatus.IN_RESCUE, "故障车辆已装载拖运", mission.task_id, now)
                elif target is RescueStatus.DELIVERED:
                    vehicle = self._vehicle_for_update(session, mission.vehicle_id)
                    self._transition_vehicle(session, vehicle, VehicleOperationalStatus.MAINTENANCE, "车辆已送达县域维修站", mission.task_id, now)
                    vehicle.current_node_id = mission.station_node_id
                    unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == mission.rescue_unit_id).with_for_update())
                    if unit is not None:
                        unit.status = "AVAILABLE"
                        unit.current_node_id = mission.station_node_id
                    order = session.scalar(select(MaintenanceOrder).where(MaintenanceOrder.task_id == mission.task_id).with_for_update())
                    if order is not None:
                        require_maintenance_transition(MaintenanceStatus(order.status), MaintenanceStatus.WAITING_BAY)
                        order.status = MaintenanceStatus.WAITING_BAY.value
                        order.next_transition_at = now + timedelta(seconds=1)
                session.flush()
                return self._case(session, mission)
        except StaleDataError as error:
            raise OptimisticLockConflict(-1) from error

    def advance_one_due_maintenance(self, now: datetime) -> OperationCaseSnapshot | None:
        active = (
            MaintenanceStatus.WAITING_BAY.value,
            MaintenanceStatus.DIAGNOSING.value,
            MaintenanceStatus.REPAIRING.value,
            MaintenanceStatus.QA_PENDING.value,
        )
        try:
            with self._session_factory() as session, session.begin():
                order = session.scalar(
                    select(MaintenanceOrder)
                    .where(MaintenanceOrder.status.in_(active), MaintenanceOrder.next_transition_at <= now)
                    .order_by(MaintenanceOrder.next_transition_at, MaintenanceOrder.id)
                    .with_for_update(skip_locked=True)
                )
                if order is None:
                    return None
                current = MaintenanceStatus(order.status)
                if current is MaintenanceStatus.QA_PENDING and order.manual_inspection_required and order.inspection_result is None:
                    order.next_transition_at = None
                    mission = session.scalar(select(RescueMission).where(RescueMission.task_id == order.task_id))
                    return self._case(session, mission)
                target = {
                    MaintenanceStatus.WAITING_BAY: MaintenanceStatus.DIAGNOSING,
                    MaintenanceStatus.DIAGNOSING: MaintenanceStatus.REPAIRING,
                    MaintenanceStatus.REPAIRING: MaintenanceStatus.QA_PENDING,
                    MaintenanceStatus.QA_PENDING: MaintenanceStatus.COMPLETED,
                }[current]
                require_maintenance_transition(current, target)
                order.status = target.value
                if target is MaintenanceStatus.DIAGNOSING:
                    order.next_transition_at = now + timedelta(seconds=5)
                elif target is MaintenanceStatus.REPAIRING:
                    order.next_transition_at = now + timedelta(minutes=order.repair_minutes)
                    order.available_after = order.next_transition_at + timedelta(seconds=6)
                elif target is MaintenanceStatus.QA_PENDING:
                    order.next_transition_at = now + timedelta(seconds=6)
                else:
                    order.next_transition_at = None
                self._event(session, order.task_id, "maintenance", order.order_no, f"MAINTENANCE_{target.value}", {"status": target.value})
                vehicle = self._vehicle_for_update(session, order.vehicle_id)
                if target is MaintenanceStatus.REPAIRING:
                    vehicle.available_after = order.available_after
                elif target is MaintenanceStatus.QA_PENDING:
                    self._transition_vehicle(session, vehicle, VehicleOperationalStatus.QA_PENDING, "维修完成，进入安全质检", order.task_id, now)
                elif target is MaintenanceStatus.COMPLETED:
                    order.inspection_result = "PASSED"
                    self._release_vehicle_and_bay(session, order, vehicle, passed=True, now=now)
                session.flush()
                mission = session.scalar(select(RescueMission).where(RescueMission.task_id == order.task_id))
                return self._case(session, mission)
        except StaleDataError as error:
            raise OptimisticLockConflict(-1) from error

    def retry_rescue(self, mission_no: str, now: datetime) -> OperationCaseSnapshot:
        try:
            with self._session_factory() as session, session.begin():
                mission = session.scalar(select(RescueMission).where(RescueMission.mission_no == mission_no).with_for_update())
                if mission is None:
                    raise VehicleOperationNotFound(mission_no)
                if mission.status != RescueStatus.FAILED.value:
                    raise InvalidStateTransition(f"Retry requires FAILED, got {mission.status}")
                unit = session.scalar(select(RescueUnit).where(RescueUnit.unit_id == mission.rescue_unit_id).with_for_update())
                if unit is None or unit.status != "AVAILABLE":
                    raise VehicleOperationsConflict("Rescue unit is not available for retry.")
                mission.status = RescueStatus.DISPATCHED.value
                mission.next_transition_at = now + timedelta(seconds=8)
                mission.failure_reason = None
                mission.attempt_count += 1
                unit.status = "DISPATCHED"
                self._event(
                    session,
                    mission.task_id,
                    "rescue",
                    mission.mission_no,
                    "RESCUE_RETRIED",
                    {"attempt_count": mission.attempt_count},
                )
                session.flush()
                return self._case(session, mission)
        except StaleDataError as error:
            raise OptimisticLockConflict(-1) from error

    def record_inspection(self, order_no: str, *, passed: bool, decided_at: datetime, decided_by: str) -> OperationCaseSnapshot:
        with self._session_factory() as session, session.begin():
            order = session.scalar(select(MaintenanceOrder).where(MaintenanceOrder.order_no == order_no).with_for_update())
            if order is None:
                raise VehicleOperationNotFound(order_no)
            if order.status != MaintenanceStatus.QA_PENDING.value:
                raise InvalidStateTransition(f"Inspection requires QA_PENDING, got {order.status}")
            target = MaintenanceStatus.COMPLETED if passed else MaintenanceStatus.FAILED
            require_maintenance_transition(MaintenanceStatus(order.status), target)
            order.status = target.value
            order.inspection_result = "PASSED" if passed else "FAILED"
            order.next_transition_at = None
            vehicle = self._vehicle_for_update(session, order.vehicle_id)
            self._release_vehicle_and_bay(session, order, vehicle, passed=passed, now=decided_at)
            self._event(session, order.task_id, "maintenance", order.order_no, "INSPECTION_DECIDED", {"passed": passed, "decided_by": decided_by})
            session.flush()
            mission = session.scalar(select(RescueMission).where(RescueMission.task_id == order.task_id))
            return self._case(session, mission)

    @staticmethod
    def _suffix(task_id: str) -> str:
        match = re.search(r"(\d+)$", task_id)
        return f"{int(match.group(1)):03d}" if match else "001"

    @staticmethod
    def _vehicle_for_update(session: Session, vehicle_id: str) -> FleetVehicle:
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == vehicle_id).with_for_update())
        if vehicle is None:
            raise VehicleOperationNotFound(vehicle_id)
        return vehicle

    def _transition_vehicle(self, session: Session, vehicle: FleetVehicle, target: VehicleOperationalStatus, reason: str, task_id: str, now: datetime) -> None:
        current = VehicleOperationalStatus(vehicle.status)
        require_vehicle_transition(current, target)
        vehicle.status = target.value
        vehicle.status_reason = reason
        vehicle.status_changed_at = now
        session.add(
            VehicleStatusHistory(
                vehicle_id=vehicle.vehicle_id, task_id=task_id, from_status=current.value, to_status=target.value, reason=reason, changed_at=now
            )
        )

    def _release_vehicle_and_bay(self, session: Session, order: MaintenanceOrder, vehicle: FleetVehicle, *, passed: bool, now: datetime) -> None:
        target = VehicleOperationalStatus.AVAILABLE if passed else VehicleOperationalStatus.OUT_OF_SERVICE
        self._transition_vehicle(session, vehicle, target, "安全质检通过，自动恢复可调度" if passed else "安全质检未通过，停止运营", order.task_id, now)
        if passed:
            vehicle.fault_code = None
            vehicle.status_reason = "安全质检通过，车辆已恢复可调度"
            vehicle.available_after = None
            vehicle.maintenance_order_no = None
        bay = session.scalar(select(MaintenanceBay).where(MaintenanceBay.bay_code == order.bay_code).with_for_update())
        if bay is not None:
            bay.status = "AVAILABLE"
            bay.current_order_no = None
        self._event(
            session, order.task_id, "vehicle", vehicle.vehicle_id, "VEHICLE_AVAILABLE" if passed else "VEHICLE_OUT_OF_SERVICE", {"status": target.value}
        )

    @staticmethod
    def _event(session: Session, task_id: str, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict[str, object]) -> None:
        session.add(
            DomainOutbox(
                event_id=f"EVT-{uuid4().hex}",
                task_id=task_id,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                payload_json=payload,
                created_at=datetime.now().astimezone(),
            )
        )

    def _case(self, session: Session, mission: RescueMission) -> OperationCaseSnapshot:
        order = session.scalar(select(MaintenanceOrder).where(MaintenanceOrder.task_id == mission.task_id))
        if order is None:
            raise VehicleOperationNotFound(mission.task_id)
        vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == mission.vehicle_id))
        if vehicle is None:
            raise VehicleOperationNotFound(mission.vehicle_id)
        replacement_event = session.scalar(
            select(DomainOutbox).where(DomainOutbox.task_id == mission.task_id, DomainOutbox.event_type == "REPLACEMENT_DISPATCHED").order_by(DomainOutbox.id)
        )
        replacement_id = str(replacement_event.payload_json["vehicle_id"]) if replacement_event is not None else None
        replacement_edge_ids = tuple(str(edge_id) for edge_id in replacement_event.payload_json.get("edge_ids", ())) if replacement_event else ()
        replacement = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == replacement_id)) if replacement_id else None
        return OperationCaseSnapshot(
            task_id=mission.task_id,
            vehicle_id=vehicle.vehicle_id,
            vehicle_status=vehicle.status,
            replacement_vehicle_id=replacement_id,
            replacement_vehicle_status=replacement.status if replacement else None,
            mission=RescueMissionSnapshot(
                mission_no=mission.mission_no,
                task_id=mission.task_id,
                vehicle_id=mission.vehicle_id,
                rescue_unit_id=mission.rescue_unit_id,
                status=RescueStatus(mission.status),
                incident_node_id=mission.incident_node_id,
                station_node_id=mission.station_node_id,
                outbound_edge_ids=tuple(mission.outbound_edge_ids),
                tow_edge_ids=tuple(mission.tow_edge_ids),
                next_transition_at=mission.next_transition_at,
                version=mission.version,
            ),
            maintenance=MaintenanceOrderSnapshot(
                order_no=order.order_no,
                task_id=order.task_id,
                vehicle_id=order.vehicle_id,
                bay_code=order.bay_code,
                status=MaintenanceStatus(order.status),
                fault_code=order.fault_code,
                diagnosis=order.diagnosis,
                repair_minutes=order.repair_minutes,
                manual_inspection_required=order.manual_inspection_required,
                next_transition_at=order.next_transition_at,
                available_after=order.available_after,
                version=order.version,
                inspection_result=order.inspection_result,
            ),
            replacement_edge_ids=replacement_edge_ids,
        )
