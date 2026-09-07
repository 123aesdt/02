from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.dispatch.models import DispatchResult
from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.fleet_vehicle import FleetVehicle
from app.models.task import DispatchTask
from app.repositories.dispatch import DispatchRepository


class VehicleReservationConflict(Exception):
    code = "VEHICLE_RESERVATION_CONFLICT"

    def __init__(self) -> None:
        super().__init__("No ranked replacement vehicle could be reserved.")


class _CandidateReservationConflict(Exception):
    pass


class DispatchService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def execute(
        self,
        task_id: str,
        order_id: int,
        original_route_id: str,
        target_route_id: str | None,
        decision: str,
        decision_reason: str,
        fallback_used: bool,
        fallback_reason: str | None,
        requires_manual_review: bool,
        recommended_action: str | None = None,
        analysis_mode: str | None = None,
        issue_subtype: str | None = None,
        original_vehicle_id: str | None = None,
        candidate_vehicles: Sequence[Mapping[str, object]] = (),
        transfer_node_id: str | None = None,
        fleet_evidence: Mapping[str, object] | None = None,
        route_evidence: Mapping[str, object] | None = None,
    ) -> DispatchResult:
        candidates = self._ranked_eligible_candidates(candidate_vehicles)
        attempts: Sequence[Mapping[str, object] | None] = candidates[:2] if candidates else (None,)
        for candidate in attempts:
            try:
                return self._execute_once(
                    task_id=task_id,
                    order_id=order_id,
                    original_route_id=original_route_id,
                    target_route_id=target_route_id,
                    decision=decision,
                    decision_reason=decision_reason,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    requires_manual_review=requires_manual_review,
                    recommended_action=recommended_action,
                    analysis_mode=analysis_mode,
                    issue_subtype=issue_subtype,
                    original_vehicle_id=original_vehicle_id,
                    candidate=candidate,
                    candidate_vehicles=candidate_vehicles,
                    transfer_node_id=transfer_node_id,
                    fleet_evidence=fleet_evidence,
                    route_evidence=route_evidence,
                )
            except _CandidateReservationConflict:
                continue
        raise VehicleReservationConflict

    def _execute_once(
        self,
        *,
        task_id: str,
        order_id: int,
        original_route_id: str,
        target_route_id: str | None,
        decision: str,
        decision_reason: str,
        fallback_used: bool,
        fallback_reason: str | None,
        requires_manual_review: bool,
        recommended_action: str | None,
        analysis_mode: str | None,
        issue_subtype: str | None,
        original_vehicle_id: str | None,
        candidate: Mapping[str, object] | None,
        candidate_vehicles: Sequence[Mapping[str, object]],
        transfer_node_id: str | None,
        fleet_evidence: Mapping[str, object] | None,
        route_evidence: Mapping[str, object] | None,
    ) -> DispatchResult:
        session = self._session_factory()
        try:
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
            if task is None:
                raise ValueError("Dispatch task does not exist")
            existing = DispatchRepository(session).get_by_task_id(task.id)
            if existing is not None:
                return self._result(existing, task_id, order_id, original_route_id, decision_reason)

            target_vehicle_id = self._text(candidate, "vehicle_id")
            target_driver_id = self._text(candidate, "driver_id")
            if candidate is not None:
                vehicle = session.scalar(
                    select(FleetVehicle).where(FleetVehicle.vehicle_id == target_vehicle_id)
                )
                if vehicle is None or vehicle.status != "AVAILABLE" or target_driver_id is None:
                    raise _CandidateReservationConflict
                vehicle.status = "RESERVED"

            manual_review = requires_manual_review or decision in {
                "MANUAL_REVIEW",
                "NO_SAFE_ROUTE",
            }
            status = (
                "REVIEW_REQUIRED"
                if manual_review
                else "REROUTED"
                if decision == "REROUTE"
                else "KEPT_ROUTE"
            )
            dispatch = Dispatch(
                dispatch_no=f"DSP-{uuid4().hex}",
                order_id=order_id,
                task_id=task.id,
                original_route_id=original_route_id,
                target_route_id=(
                    target_route_id
                    if manual_review
                    else target_route_id or original_route_id
                ),
                original_vehicle_id=original_vehicle_id,
                target_vehicle_id=target_vehicle_id,
                target_driver_id=target_driver_id,
                transfer_node_id=transfer_node_id,
                decision_reason=decision_reason,
                recommended_action=recommended_action
                or ("保持任务暂停并等待人工复核。" if manual_review else None),
                analysis_mode=analysis_mode
                or ("EIGHT_AGENT_RULE_ASSISTED" if manual_review else None),
                issue_subtype=issue_subtype or ("GENERAL" if manual_review else None),
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                status=status,
            )
            session.add(dispatch)
            session.flush()
            session.add_all(
                [
                    DispatchEvidence(
                        dispatch_id=dispatch.id,
                        evidence_type="FLEET_ALLOCATION",
                        algorithm_version=self._algorithm_version(
                            fleet_evidence,
                            "FLEET_SCORE_V1",
                        ),
                        payload_json=self._compact_fleet_evidence(
                            candidate_vehicles,
                            target_vehicle_id,
                        ),
                    ),
                    DispatchEvidence(
                        dispatch_id=dispatch.id,
                        evidence_type="ROUTE_CALCULATION",
                        algorithm_version=self._algorithm_version(
                            route_evidence,
                            "DIJKSTRA_V1",
                        ),
                        payload_json=self._compact_route_evidence(
                            route_evidence,
                            target_route_id,
                        ),
                        road_network_version=self._integer(
                            None
                            if route_evidence is None
                            else route_evidence.get("road_network_version")
                        ),
                    ),
                ]
            )
            session.commit()
            return DispatchResult(
                dispatch.id,
                dispatch.dispatch_no,
                order_id,
                task_id,
                status,
                original_route_id,
                dispatch.target_route_id,
                dispatch.version,
                not manual_review,
                decision_reason,
                manual_review,
                original_vehicle_id,
                target_vehicle_id,
                target_driver_id,
            )
        except StaleDataError as error:
            session.rollback()
            raise _CandidateReservationConflict from error
        except IntegrityError:
            session.rollback()
            existing_result = self._read_idempotent_result(
                task_id=task_id,
                order_id=order_id,
                original_route_id=original_route_id,
                decision_reason=decision_reason,
            )
            if existing_result is not None:
                return existing_result
            raise
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _read_idempotent_result(
        self,
        *,
        task_id: str,
        order_id: int,
        original_route_id: str,
        decision_reason: str,
    ) -> DispatchResult | None:
        with self._session_factory() as session:
            task = session.scalar(
                select(DispatchTask).where(DispatchTask.task_id == task_id)
            )
            if task is None:
                return None
            existing = DispatchRepository(session).get_by_task_id(task.id)
            if existing is None:
                return None
            return self._result(
                existing,
                task_id,
                order_id,
                original_route_id,
                decision_reason,
            )

    @staticmethod
    def _result(
        dispatch: Dispatch,
        task_id: str,
        order_id: int,
        original_route_id: str,
        decision_reason: str,
    ) -> DispatchResult:
        manual_review = dispatch.status == "REVIEW_REQUIRED"
        return DispatchResult(
            dispatch.id,
            dispatch.dispatch_no,
            order_id,
            task_id,
            dispatch.status,
            dispatch.original_route_id or original_route_id,
            dispatch.target_route_id,
            dispatch.version,
            not manual_review,
            dispatch.decision_reason or decision_reason,
            manual_review,
            dispatch.original_vehicle_id,
            dispatch.target_vehicle_id,
            dispatch.target_driver_id,
        )

    @staticmethod
    def _ranked_eligible_candidates(
        candidates: Sequence[Mapping[str, object]],
    ) -> tuple[Mapping[str, object], ...]:
        return tuple(
            candidate for candidate in candidates if candidate.get("eligible") is True
        )

    @staticmethod
    def _text(value: Mapping[str, object] | None, key: str) -> str | None:
        item = None if value is None else value.get(key)
        return item if isinstance(item, str) and item else None

    @staticmethod
    def _integer(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _algorithm_version(
        evidence: Mapping[str, object] | None,
        default: str,
    ) -> str:
        value = None if evidence is None else evidence.get("algorithm_version")
        return value if isinstance(value, str) and value else default

    @classmethod
    def _compact_fleet_evidence(
        cls,
        candidates: Sequence[Mapping[str, object]],
        selected_vehicle_id: str | None,
    ) -> dict[str, Any]:
        return {
            "selected_vehicle_id": selected_vehicle_id,
            "candidates": [
                {
                    "vehicle_id": cls._text(candidate, "vehicle_id"),
                    "driver_id": cls._text(candidate, "driver_id"),
                    "score": candidate.get("score"),
                    "eligible": candidate.get("eligible") is True,
                    "exclusion_reasons": [
                        reason
                        for reason in candidate.get("exclusion_reasons", [])
                        if isinstance(reason, str)
                    ],
                }
                for candidate in candidates
            ],
        }

    @classmethod
    def _compact_route_evidence(
        cls,
        evidence: Mapping[str, object] | None,
        target_route_id: str | None,
    ) -> dict[str, Any]:
        source = evidence or {}
        recommended = source.get("recommended_path")
        recommended_path = recommended if isinstance(recommended, Mapping) else {}
        routes = source.get("candidate_routes")
        candidate_routes = routes if isinstance(routes, Sequence) and not isinstance(routes, str) else ()
        return {
            "target_route_id": target_route_id,
            "blocked_edge_ids": cls._string_list(source.get("blocked_edge_ids")),
            "recommended_path": {
                "node_ids": cls._string_list(recommended_path.get("node_ids")),
                "edge_ids": cls._string_list(recommended_path.get("edge_ids")),
            },
            "candidate_routes": [
                {
                    "route_id": cls._text(route, "route_id"),
                    "node_ids": cls._string_list(route.get("node_ids")),
                    "edge_ids": cls._string_list(route.get("edge_ids")),
                    "score": route.get("score"),
                }
                for route in candidate_routes
                if isinstance(route, Mapping)
            ],
        }

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [item for item in value if isinstance(item, str)]
