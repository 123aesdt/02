from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select

from app.api.v1.schemas import (
    CreateDispatchTaskRequest,
    PathResponse,
    RoadEdgeResponse,
    RoadNodeResponse,
    RouteCandidateResponse,
    RoutePlanResponse,
    VehicleAllocationResponse,
    VehicleCandidateResponse,
)
from app.events.broker import TaskEventBroker
from app.events.models import TaskEvent, TaskEventType
from app.idempotency.service import IdempotencyService
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.dispatch_publication import DispatchPublication
from app.models.task import DispatchTask
from app.observability.context import current_correlation_id
from app.streams.errors import QueueConnectionError
from app.streams.models import DispatchTaskMessage
from app.streams.redis_queue import RedisStreamQueue


class TaskNotFoundError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass


class SubmissionQueueError(Exception):
    pass


class AssigneeNotFoundError(Exception):
    pass


class TaskAccessForbiddenError(Exception):
    pass


class DispatchTaskApiService:
    def __init__(self, session_factory, queue: RedisStreamQueue, *, event_broker: TaskEventBroker | None = None) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._idempotency = IdempotencyService(session_factory)
        self._event_broker = event_broker

    async def submit(
        self,
        request: CreateDispatchTaskRequest,
        *,
        assignee_subject_id: str,
    ) -> dict[str, object]:
        if request.assignee_employee_id is not None:
            self._require_active_delivery_employee(assignee_subject_id)
        existing = self._by_key(request.idempotency_key)
        if existing is not None:
            if existing.order_id != request.order_id or existing.assignee_subject_id != assignee_subject_id:
                raise IdempotencyConflictError
            if existing.status == "SUBMISSION_FAILED":
                return await self._publish_existing(existing, request)
            return self._accepted(existing, duplicate=True)
        task_id = f"TASK-{uuid4().hex[:31]}"
        decision = self._idempotency.begin(
            task_id,
            request.order_id,
            request.idempotency_key,
            anomaly_id=request.anomaly_id,
            assignee_subject_id=assignee_subject_id,
        )
        if not decision.should_execute:
            return self._accepted(self._task(decision.task_id), duplicate=True)
        message = DispatchTaskMessage(
            "1",
            task_id,
            request.order_id,
            request.anomaly_id,
            request.idempotency_key,
            datetime.now(UTC).isoformat(),
            {
                "driver_id": request.driver_id,
                "vehicle_id": request.vehicle_id,
                "route_id": request.route_id,
                "anomaly_type": request.anomaly_type,
                "anomaly_description": request.anomaly_description,
                "vehicle_status": request.vehicle_status,
            },
            current_correlation_id(),
        )
        try:
            await self._queue.publish(message)
        except QueueConnectionError as error:
            self._idempotency.mark_terminal(task_id, "SUBMISSION_FAILED")
            raise SubmissionQueueError from error
        await self._publish_accepted(task_id)
        return self._accepted(self._task(task_id), duplicate=False)

    async def _publish_existing(self, task: DispatchTask, request: CreateDispatchTaskRequest) -> dict[str, object]:
        message = DispatchTaskMessage(
            "1",
            task.task_id,
            task.order_id,
            request.anomaly_id,
            task.idempotency_key,
            datetime.now(UTC).isoformat(),
            {
                "driver_id": request.driver_id,
                "vehicle_id": request.vehicle_id,
                "route_id": request.route_id,
                "anomaly_type": request.anomaly_type,
                "anomaly_description": request.anomaly_description,
                "vehicle_status": request.vehicle_status,
            },
            current_correlation_id(),
        )
        try:
            await self._queue.publish(message)
        except QueueConnectionError as error:
            raise SubmissionQueueError from error
        self._set_submission_pending(task.task_id)
        await self._publish_accepted(task.task_id)
        return self._accepted(self._task(task.task_id), duplicate=True)

    async def _publish_accepted(self, task_id: str) -> None:
        if self._event_broker is None:
            return
        try:
            await self._event_broker.publish(TaskEvent.create(task_id, TaskEventType.TASK_ACCEPTED, "api", "PENDING"))
        except Exception:
            return

    def status(self, task_id: str) -> dict[str, object]:
        task = self._task(task_id)
        status = self._api_status(task.status)
        return {
            "task_id": task.task_id,
            "order_id": task.order_id,
            "status": status,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "created_at": task.created_at,
            "ready": status in {"COMPLETED", "REVIEW_REQUIRED"},
            "requires_manual_review": status == "REVIEW_REQUIRED",
        }

    def result(self, task_id: str, *, include_unpublished: bool = True) -> dict[str, object]:
        task = self._task(task_id)
        status = self._api_status(task.status)
        if task.status not in {"APPROVED", "COMPLETED", "REVIEW_REQUIRED"}:
            return {"task_id": task.task_id, "order_id": task.order_id, "ready": False, "status": status}
        with self._session_factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.task_id == task.id))
            evidence_rows = (
                []
                if dispatch is None
                else list(session.scalars(select(DispatchEvidence).where(DispatchEvidence.dispatch_id == dispatch.id).order_by(DispatchEvidence.id)))
            )
            audit = session.scalar(select(AuditRecord).where(AuditRecord.task_id == task.id))
            publication = session.scalar(select(DispatchPublication).where(DispatchPublication.task_id == task.id))
            recipient = None
            if task.assignee_subject_id is not None:
                recipient = session.get(DemoEmployeeAccount, task.assignee_subject_id)
            recipient_employee_id = task.assignee_subject_id
            recipient_display_name = recipient.display_name if recipient is not None else task.assignee_subject_id
            route_visible = include_unpublished or publication is not None
            vehicle_allocation = None
            route_plan = None
            if route_visible and dispatch is not None:
                vehicle_allocation, route_plan = self._evidence_responses(dispatch, evidence_rows)
            return {
                "task_id": task.task_id,
                "order_id": task.order_id,
                "ready": True,
                "status": status,
                "dispatch": None
                if dispatch is None
                else {
                    "dispatch_id": dispatch.id,
                    "dispatch_no": dispatch.dispatch_no,
                    "original_route_id": dispatch.original_route_id,
                    "target_route_id": dispatch.target_route_id if route_visible else None,
                    "decision_reason": dispatch.decision_reason if route_visible else None,
                    "fallback_used": dispatch.fallback_used,
                    "fallback_reason": dispatch.fallback_reason,
                    "version": dispatch.version,
                    "status": dispatch.status,
                    "executed": dispatch.status in {"EXECUTED", "COMPLETED", "KEPT_ROUTE", "REROUTED"},
                },
                "audit": None
                if audit is None
                else {
                    "result": audit.result,
                    "reason": audit.reason,
                    "dispatch_id": audit.dispatch_id,
                    "created_at": audit.created_at,
                },
                "publication": {
                    "status": "PENDING" if publication is None else publication.status,
                    "route_id": None if publication is None else publication.route_id,
                    "route_instruction": None if publication is None else publication.route_instruction,
                    "published_at": None if publication is None else self._aware(publication.published_at),
                    "published_by": None if publication is None else publication.published_by_display_name,
                    "recipient_employee_id": recipient_employee_id,
                    "recipient_display_name": recipient_display_name,
                },
                "vehicle_allocation": vehicle_allocation,
                "route_plan": route_plan,
            }

    @classmethod
    def _evidence_responses(
        cls,
        dispatch: Dispatch,
        evidence_rows: Sequence[DispatchEvidence],
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if len(evidence_rows) != 2:
            return None, None
        by_type = {row.evidence_type: row for row in evidence_rows}
        if set(by_type) != {"FLEET_ALLOCATION", "ROUTE_CALCULATION"}:
            return None, None
        fleet_row = by_type["FLEET_ALLOCATION"]
        route_row = by_type["ROUTE_CALCULATION"]
        if not isinstance(fleet_row.payload_json, Mapping) or not isinstance(route_row.payload_json, Mapping):
            return None, None
        try:
            candidates = cls._vehicle_candidates(fleet_row.payload_json, dispatch.target_vehicle_id)
            pickup_source = fleet_row.payload_json.get("pickup_route")
            if pickup_source is None:
                pickup_source = route_row.payload_json.get("pickup_path")
            allocation = VehicleAllocationResponse.model_validate(
                {
                    "original_vehicle_id": dispatch.original_vehicle_id,
                    "target_vehicle_id": dispatch.target_vehicle_id,
                    "target_driver_id": dispatch.target_driver_id,
                    "vehicle_reassigned": dispatch.target_vehicle_id is not None and dispatch.target_vehicle_id != dispatch.original_vehicle_id,
                    "candidate_vehicles": candidates,
                    "pickup_route": cls._path(pickup_source),
                    "scoring_formula": fleet_row.algorithm_version,
                }
            )
            recommended = cls._path(route_row.payload_json.get("recommended_path"))
            route_plan = RoutePlanResponse.model_validate(
                {
                    "original_path": cls._path(route_row.payload_json.get("original_path")),
                    "recommended_path": recommended,
                    "candidate_routes": cls._route_candidates(route_row.payload_json.get("candidate_routes")),
                    "blocked_edge_ids": cls._string_list(route_row.payload_json.get("blocked_edge_ids")),
                    "distance_delta_km": route_row.payload_json.get("distance_delta_km"),
                    "eta_delta_minutes": route_row.payload_json.get("eta_delta_minutes"),
                    "visited_node_count": route_row.payload_json.get("visited_node_count")
                    if "visited_node_count" in route_row.payload_json
                    else (None if recommended is None else recommended.get("visited_node_count")),
                    "routing_status": route_row.payload_json.get("routing_status"),
                    "algorithm": route_row.algorithm_version,
                    "road_network_version": route_row.road_network_version,
                    "network_nodes": cls._road_nodes(route_row.payload_json.get("network_nodes")),
                    "network_edges": cls._road_edges(route_row.payload_json.get("network_edges")),
                }
            )
        except (TypeError, ValueError, ValidationError):
            return None, None
        return allocation.model_dump(mode="json"), route_plan.model_dump(mode="json")

    @classmethod
    def _vehicle_candidates(cls, payload: Mapping[str, object], target_vehicle_id: str | None) -> list[dict[str, object]]:
        raw_candidates = cls._mapping_list(payload.get("candidates"))
        selected = payload.get("selected_candidate")
        selected_candidate = selected if isinstance(selected, Mapping) else {}
        output: list[dict[str, object]] = []
        for candidate in raw_candidates:
            source = dict(candidate)
            if source.get("vehicle_id") == target_vehicle_id:
                source.update(selected_candidate)
            output.append(VehicleCandidateResponse.model_validate(cls._pick(source, cls._vehicle_candidate_keys())).model_dump(mode="json"))
        return output

    @classmethod
    def _route_candidates(cls, value: object) -> list[dict[str, object]]:
        return [
            RouteCandidateResponse.model_validate(cls._pick(candidate, cls._route_candidate_keys())).model_dump(mode="json")
            for candidate in cls._mapping_list(value)
        ]

    @classmethod
    def _road_nodes(cls, value: object) -> list[dict[str, object]]:
        keys = ("node_id", "name", "x_km", "y_km", "node_type")
        return [RoadNodeResponse.model_validate(cls._pick(node, keys)).model_dump(mode="json") for node in cls._mapping_list(value)]

    @classmethod
    def _road_edges(cls, value: object) -> list[dict[str, object]]:
        keys = (
            "edge_id",
            "name",
            "from_node_id",
            "to_node_id",
            "distance_km",
            "base_minutes",
            "road_level",
            "risk_level",
            "status",
            "congestion_factor",
            "weight_limit_tons",
            "bidirectional",
            "version",
        )
        return [RoadEdgeResponse.model_validate(cls._pick(edge, keys)).model_dump(mode="json") for edge in cls._mapping_list(value)]

    @classmethod
    def _path(cls, value: object) -> dict[str, object] | None:
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("Path evidence must be an object.")
        keys = (
            "objective",
            "node_ids",
            "edge_ids",
            "distance_km",
            "estimated_minutes",
            "risk_cost",
            "visited_node_count",
            "scoring_formula",
        )
        return PathResponse.model_validate(cls._pick(value, keys)).model_dump(mode="json")

    @staticmethod
    def _pick(source: Mapping[str, object], keys: Sequence[str]) -> dict[str, object]:
        return {key: source[key] for key in keys if key in source}

    @staticmethod
    def _mapping_list(value: object) -> list[Mapping[str, object]]:
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise ValueError("Evidence list is invalid.")
        return value

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("Evidence identifier list is invalid.")
        return value

    @staticmethod
    def _vehicle_candidate_keys() -> tuple[str, ...]:
        return (
            "vehicle_id",
            "driver_id",
            "vehicle_status",
            "driver_status",
            "remaining_capacity_kg",
            "gross_weight_tons",
            "cargo_capability",
            "pickup_route",
            "pickup_distance_km",
            "pickup_eta_minutes",
            "score",
            "score_components",
            "scoring_formula",
            "eligible",
            "exclusion_reasons",
        )

    @staticmethod
    def _route_candidate_keys() -> tuple[str, ...]:
        return (
            "route_id",
            "route_name",
            "objective",
            "node_ids",
            "edge_ids",
            "distance_km",
            "estimated_minutes",
            "risk_level",
            "risk_cost",
            "visited_node_count",
            "available",
            "reason",
            "score",
            "score_components",
            "scoring_formula",
            "algorithm_version",
            "road_network_version",
        )

    def require_read_access(
        self,
        task_id: str,
        *,
        subject_id: str,
        can_read_all: bool,
    ) -> None:
        task = self._task(task_id)
        if not can_read_all and task.assignee_subject_id != subject_id:
            raise TaskAccessForbiddenError

    def _require_active_delivery_employee(self, employee_id: str) -> None:
        with self._session_factory() as session:
            account = session.get(DemoEmployeeAccount, employee_id)
            if account is None or not account.is_active or account.role != "EMPLOYEE":
                raise AssigneeNotFoundError

    def _by_key(self, key: str) -> DispatchTask | None:
        with self._session_factory() as session:
            return session.scalar(select(DispatchTask).where(DispatchTask.idempotency_key == key))

    def _task(self, task_id: str) -> DispatchTask:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise TaskNotFoundError
            return task

    def _set_submission_pending(self, task_id: str) -> None:
        with self._session_factory() as session:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise TaskNotFoundError
            task.status = "PENDING"
            task.completed_at = None
            session.commit()

    @staticmethod
    def _accepted(task: DispatchTask, *, duplicate: bool) -> dict[str, object]:
        return {
            "task_id": task.task_id,
            "order_id": task.order_id,
            "status": task.status,
            "accepted": True,
            "duplicate": duplicate,
            "message": "Dispatch task accepted for asynchronous processing.",
        }

    @staticmethod
    def _api_status(status: str) -> str:
        return "COMPLETED" if status == "APPROVED" else status

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None or value.utcoffset() is None else value
