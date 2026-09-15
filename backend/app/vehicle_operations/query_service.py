from datetime import UTC, datetime

from sqlalchemy import select

from app.models.fleet_vehicle import FleetVehicle
from app.models.road import RoadEdge, RoadNode
from app.models.task import DispatchTask
from app.models.vehicle_operation import DomainOutbox, MaintenanceOrder, RescueMission
from app.vehicle_operations.models import MaintenanceStatus, RescueStatus
from app.vehicle_operations.sqlalchemy_repository import VehicleOperationNotFound


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class VehicleOperationsQueryService:
    def __init__(self, session_factory, repository, *, clock=None) -> None:
        self._session_factory = session_factory
        self._repository = repository
        self._clock = clock or SystemClock().now

    def map_snapshot(self, task_id: str) -> dict[str, object]:
        case = self._repository.get_case(task_id)
        if case is None:
            raise VehicleOperationNotFound(task_id)
        now = self._clock()
        with self._session_factory() as session:
            nodes = list(session.scalars(select(RoadNode).order_by(RoadNode.node_id)))
            edges = list(session.scalars(select(RoadEdge).order_by(RoadEdge.edge_id)))
            vehicles = list(session.scalars(select(FleetVehicle).order_by(FleetVehicle.vehicle_id)))
            events = list(session.scalars(select(DomainOutbox).where(DomainOutbox.task_id == task_id).order_by(DomainOutbox.id)))
        interrupted = ["E03"] if any(edge.edge_id == "E03" for edge in edges) else []
        edge_by_id = {edge.edge_id: edge for edge in edges}
        route_specs = (
            ("REPLACEMENT", case.replacement_edge_ids, "ACTIVE", None, case.mission.incident_node_id),
            ("RESCUE", case.mission.outbound_edge_ids, case.mission.status.value, None, case.mission.incident_node_id),
            ("TOW", case.mission.tow_edge_ids, case.mission.status.value, case.mission.incident_node_id, None),
            ("INTERRUPTED", tuple(interrupted), "INTERRUPTED", None, None),
        )
        return {
            "task_id": task_id,
            "generated_at": now.isoformat(),
            "incident": {
                "status": "AUTO_PROCESSING" if case.vehicle_status != "AVAILABLE" else "RECOVERED",
                "risk": "HIGH",
                "vehicle_id": case.vehicle_id,
                "replacement_vehicle_id": case.replacement_vehicle_id,
                "location_node_id": case.mission.incident_node_id,
                "fault_code": case.maintenance.fault_code,
                "cargo": "冷链生鲜 · 700kg",
            },
            "nodes": [
                {
                    "node_id": node.node_id,
                    "name": node.name,
                    "x_km": format(node.x_km, "f"),
                    "y_km": format(node.y_km, "f"),
                    "node_type": node.node_type,
                }
                for node in nodes
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "name": edge.name,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "road_level": edge.road_level,
                    "status": edge.status,
                }
                for edge in edges
            ],
            "vehicles": [
                {
                    "vehicle_id": vehicle.vehicle_id,
                    "plate_no": vehicle.plate_no,
                    "status": vehicle.status,
                    "current_node_id": vehicle.current_node_id,
                    "max_load_kg": format(vehicle.max_load_kg, "f"),
                    "current_load_kg": format(vehicle.current_load_kg, "f"),
                    "assigned_driver_id": vehicle.assigned_driver_id,
                    "status_reason": vehicle.status_reason,
                    "available_after": vehicle.available_after.isoformat() if vehicle.available_after else None,
                    "is_incident": vehicle.vehicle_id == case.vehicle_id,
                    "is_replacement": vehicle.vehicle_id == case.replacement_vehicle_id,
                }
                for vehicle in vehicles
            ],
            "routes": [
                {
                    "kind": kind,
                    "edge_ids": list(edge_ids),
                    "node_ids": self._ordered_route_nodes(edge_ids, edge_by_id, start_node_id=start, end_node_id=end),
                    "status": status,
                }
                for kind, edge_ids, status, start, end in route_specs
            ],
            "rescue": self._rescue(case),
            "maintenance": self._maintenance(case, now),
            "stages": self._stages(case),
            "timeline": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "label": self._event_label(event.event_type),
                    "timestamp": event.created_at.isoformat(),
                    "payload": event.payload_json,
                }
                for event in events
            ],
        }

    def list_vehicles(self) -> list[dict[str, object]]:
        with self._session_factory() as session:
            return [
                {
                    "vehicle_id": row.vehicle_id,
                    "plate_no": row.plate_no,
                    "vehicle_type": row.vehicle_type,
                    "status": row.status,
                    "current_node_id": row.current_node_id,
                    "fault_code": row.fault_code,
                    "maintenance_order_no": row.maintenance_order_no,
                    "version": row.version,
                }
                for row in session.scalars(select(FleetVehicle).order_by(FleetVehicle.vehicle_id))
            ]

    def driver_map_snapshot(self, task_id: str, principal) -> dict[str, object]:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
        if task is None or task.assignee_subject_id != principal.subject_id:
            raise VehicleOperationNotFound(task_id)
        return self.map_snapshot(task_id)

    def get_rescue_mission(self, mission_no: str) -> dict[str, object]:
        with self._session_factory() as session:
            mission = session.scalar(select(RescueMission).where(RescueMission.mission_no == mission_no))
            if mission is None:
                raise VehicleOperationNotFound(mission_no)
            case = self._repository.get_case(mission.task_id)
            assert case is not None
            return self._rescue(case)

    def retry_rescue_mission(self, mission_no: str) -> dict[str, object]:
        retry = getattr(self._repository, "retry_rescue", None)
        if retry is None:
            raise VehicleOperationNotFound(mission_no)
        return retry(mission_no, self._clock())

    def list_maintenance_orders(self) -> list[dict[str, object]]:
        with self._session_factory() as session:
            order_nos = list(session.scalars(select(MaintenanceOrder.order_no).order_by(MaintenanceOrder.id.desc())))
        return [self.get_maintenance_order(order_no) for order_no in order_nos]

    def get_maintenance_order(self, order_no: str) -> dict[str, object]:
        with self._session_factory() as session:
            row = session.scalar(select(MaintenanceOrder).where(MaintenanceOrder.order_no == order_no))
            if row is None:
                raise VehicleOperationNotFound(order_no)
            case = self._repository.get_case(row.task_id)
            assert case is not None
            return self._maintenance(case, self._clock())

    def record_inspection(self, order_no: str, passed: bool, principal) -> dict[str, object]:
        case = self._repository.record_inspection(
            order_no,
            passed=passed,
            decided_at=self._clock(),
            decided_by=principal.subject_id,
        )
        return self._maintenance(case, self._clock())

    @staticmethod
    def _rescue(case) -> dict[str, object]:
        return {
            "mission_no": case.mission.mission_no,
            "status": case.mission.status.value,
            "progress_percent": case.mission.progress_percent,
            "rescue_unit_id": case.mission.rescue_unit_id,
            "incident_node_id": case.mission.incident_node_id,
            "station_node_id": case.mission.station_node_id,
            "outbound_edge_ids": list(case.mission.outbound_edge_ids),
            "tow_edge_ids": list(case.mission.tow_edge_ids),
            "next_transition_at": case.mission.next_transition_at.isoformat() if case.mission.next_transition_at else None,
        }

    @staticmethod
    def _maintenance(case, now: datetime) -> dict[str, object]:
        return {
            "order_no": case.maintenance.order_no,
            "vehicle_id": case.maintenance.vehicle_id,
            "bay_code": case.maintenance.bay_code,
            "status": case.maintenance.status.value,
            "fault_code": case.maintenance.fault_code,
            "diagnosis": case.maintenance.diagnosis,
            "repair_minutes": case.maintenance.repair_minutes,
            "manual_inspection_required": case.maintenance.manual_inspection_required,
            "inspection_result": case.maintenance.inspection_result,
            "progress_percent": case.maintenance.progress_percent,
            "countdown_seconds": case.maintenance.seconds_remaining(now),
            "available_after": case.maintenance.available_after.isoformat() if case.maintenance.available_after else None,
        }

    @staticmethod
    def _stages(case) -> list[dict[str, object]]:
        rescue_progress = case.mission.progress_percent
        maintenance_progress = case.maintenance.progress_percent
        rescue_status = case.mission.status
        maintenance_status = case.maintenance.status
        replacement_status = "COMPLETED" if case.replacement_vehicle_id else "SKIPPED"
        replacement_detail = (
            f"{case.replacement_vehicle_id} 已接管配送"
            if case.replacement_vehicle_id
            else "当前任务未启用替代车辆"
        )
        rescue_stage_status = {
            RescueStatus.DELIVERED: "COMPLETED",
            RescueStatus.FAILED: "FAILED",
            RescueStatus.CANCELLED: "CANCELLED",
            RescueStatus.CREATED: "WAITING",
        }.get(rescue_status, "ACTIVE")
        maintenance_stage_status = {
            MaintenanceStatus.COMPLETED: "COMPLETED",
            MaintenanceStatus.FAILED: "FAILED",
            MaintenanceStatus.CANCELLED: "CANCELLED",
        }.get(
            maintenance_status,
            "ACTIVE" if rescue_status is RescueStatus.DELIVERED else "WAITING",
        )
        return [
            {"key": "SAFE_STOP", "title": "安全停车", "status": "COMPLETED", "detail": "停车确认、冷链保温与道路警示已完成"},
            {"key": "REPLACEMENT", "title": "替代配送接管", "status": replacement_status, "detail": replacement_detail},
            {"key": "RESCUE", "title": "救援运送", "status": rescue_stage_status, "detail": f"救援进度 {rescue_progress}%"},
            {
                "key": "MAINTENANCE",
                "title": "维修与自动复岗",
                "status": maintenance_stage_status,
                "detail": f"维修进度 {maintenance_progress}%",
            },
        ]

    @staticmethod
    def _event_label(event_type: str) -> str:
        return {
            "VEHICLE_STOPPED": "发现故障，车辆已安全停车",
            "REPLACEMENT_DISPATCHED": "系统分配替代车辆接管配送",
            "RESCUE_DISPATCHED": "道路救援车辆已出发",
            "MAINTENANCE_SCHEDULED": "维修工位已预留",
            "RESCUE_ARRIVED": "救援车辆已抵达故障点",
            "VEHICLE_LOADED": "故障车辆已装载拖运",
            "TOW_DELIVERED": "故障车辆已送达维修站",
            "MAINTENANCE_DIAGNOSING": "维修人员开始故障诊断",
            "MAINTENANCE_REPAIRING": "车辆开始维修",
            "MAINTENANCE_QA_PENDING": "维修完成，等待安全质检",
            "MAINTENANCE_COMPLETED": "安全质检通过，维修工单完成",
            "MAINTENANCE_FAILED": "维修或安全质检未通过",
            "MAINTENANCE_CANCELLED": "维修工单已取消",
            "RESCUE_RETRIED": "道路救援任务已重新派发",
            "VEHICLE_AVAILABLE": "质检通过，车辆自动恢复可调度",
            "VEHICLE_OUT_OF_SERVICE": "质检未通过，车辆停止运营",
            "INSPECTION_DECIDED": "安全质检结果已确认",
        }.get(event_type, event_type.replace("_", " "))

    @staticmethod
    def _ordered_route_nodes(edge_ids, edge_by_id, *, start_node_id=None, end_node_id=None) -> list[str]:
        if not edge_ids:
            return []
        reverse = start_node_id is None and end_node_id is not None
        ordered_edges = list(reversed(edge_ids)) if reverse else list(edge_ids)
        current = end_node_id if reverse else start_node_id
        first = edge_by_id.get(ordered_edges[0])
        if first is None:
            return []
        if current is None:
            current = first.from_node_id
        nodes = [current]
        for edge_id in ordered_edges:
            edge = edge_by_id.get(edge_id)
            if edge is None:
                return []
            if edge.from_node_id == current:
                current = edge.to_node_id
            elif edge.to_node_id == current:
                current = edge.from_node_id
            else:
                return []
            nodes.append(current)
        return list(reversed(nodes)) if reverse else nodes
