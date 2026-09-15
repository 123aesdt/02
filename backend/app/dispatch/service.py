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
                vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == target_vehicle_id))
                if vehicle is None or vehicle.status != "AVAILABLE" or target_driver_id is None:
                    raise _CandidateReservationConflict
                vehicle.status = "RESERVED"

            manual_review = requires_manual_review or decision in {
                "MANUAL_REVIEW",
                "NO_SAFE_ROUTE",
            }
            status = "REVIEW_REQUIRED" if manual_review else "REROUTED" if decision == "REROUTE" else "KEPT_ROUTE"
            dispatch = Dispatch(
                dispatch_no=f"DSP-{uuid4().hex}",
                order_id=order_id,
                task_id=task.id,
                original_route_id=original_route_id,
                target_route_id=(target_route_id if manual_review else target_route_id or original_route_id),
                original_vehicle_id=original_vehicle_id,
                target_vehicle_id=target_vehicle_id,
                target_driver_id=target_driver_id,
                transfer_node_id=transfer_node_id,
                decision_reason=decision_reason,
                recommended_action=recommended_action or ("保持任务暂停并等待人工复核。" if manual_review else None),
                analysis_mode=analysis_mode or ("EIGHT_AGENT_RULE_ASSISTED" if manual_review else None),
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
                            original_vehicle_id,
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
                            original_route_id,
                            target_route_id,
                        ),
                        road_network_version=self._integer(None if route_evidence is None else route_evidence.get("road_network_version")),
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
            task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
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
        return tuple(candidate for candidate in candidates if candidate.get("eligible") is True)

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
        original_vehicle_id: str | None,
        selected_vehicle_id: str | None,
    ) -> dict[str, Any]:
        selected = next(
            (candidate for candidate in candidates if cls._text(candidate, "vehicle_id") == selected_vehicle_id),
            None,
        )
        return {
            "original_vehicle_id": original_vehicle_id,
            "target_vehicle_id": selected_vehicle_id,
            "target_driver_id": cls._text(selected, "driver_id"),
            "vehicle_reassigned": selected_vehicle_id is not None and selected_vehicle_id != original_vehicle_id,
            "pickup_route": cls._compact_path(None if selected is None else selected.get("pickup_route")),
            "selected_candidate": (cls._compact_selected_candidate(selected) if selected is not None else None),
            "candidates": [
                cls._compact_vehicle_candidate(candidate)
                if cls._text(candidate, "vehicle_id") == selected_vehicle_id
                else {
                    "vehicle_id": cls._text(candidate, "vehicle_id"),
                    "score": cls._number_text(candidate.get("score")),
                    "exclusion_reasons": cls._string_list(candidate.get("exclusion_reasons")),
                }
                for candidate in candidates
            ],
        }

    @classmethod
    def _compact_selected_candidate(
        cls,
        candidate: Mapping[str, object],
    ) -> dict[str, object]:
        remaining_capacity = candidate.get("remaining_capacity_kg")
        if remaining_capacity is None:
            remaining_capacity = candidate.get("remaining_load_kg")
        score_components = candidate.get("score_components")
        components = score_components if isinstance(score_components, Mapping) else {}
        allowed_component_keys = (
            "eta_penalty",
            "distance_penalty",
            "load_penalty",
            "road_risk_penalty",
            "same_station_bonus",
            "cargo_exact_match_bonus",
        )
        return {
            "vehicle_id": cls._text(candidate, "vehicle_id"),
            "driver_id": cls._text(candidate, "driver_id"),
            "vehicle_status": cls._text(candidate, "vehicle_status"),
            "driver_status": cls._text(candidate, "driver_status"),
            "remaining_capacity_kg": cls._number_text(remaining_capacity),
            "cargo_capability": cls._text(candidate, "cargo_capability"),
            "score": cls._number_text(candidate.get("score")),
            "score_components": {key: cls._number_text(components.get(key)) for key in allowed_component_keys if components.get(key) is not None},
            "eligible": candidate.get("eligible") is True,
            "exclusion_reasons": cls._string_list(candidate.get("exclusion_reasons")),
        }

    @classmethod
    def _compact_vehicle_candidate(
        cls,
        candidate: Mapping[str, object],
    ) -> dict[str, object]:
        compact = cls._compact_selected_candidate(candidate)
        compact.update(
            {
                "gross_weight_tons": cls._number_text(candidate.get("gross_weight_tons")),
                "pickup_route": cls._compact_path(candidate.get("pickup_route")),
                "pickup_distance_km": cls._number_text(candidate.get("pickup_distance_km")),
                "pickup_eta_minutes": cls._integer(candidate.get("pickup_eta_minutes")),
                "scoring_formula": cls._text(candidate, "scoring_formula"),
            }
        )
        return compact

    @classmethod
    def _compact_route_evidence(
        cls,
        evidence: Mapping[str, object] | None,
        original_route_id: str,
        target_route_id: str | None,
    ) -> dict[str, Any]:
        source = evidence or {}
        original_path = cls._compact_path(source.get("original_path"))
        recommended_path = cls._compact_path(source.get("recommended_path"))
        pickup_path = cls._compact_path(source.get("pickup_path") if source.get("pickup_path") is not None else source.get("pickup_route"))
        blocked_edge_ids = cls._string_list(source.get("blocked_edge_ids"))
        relevant_edge_ids = set(blocked_edge_ids)
        for path in (original_path, recommended_path, pickup_path):
            if path is not None:
                relevant_edge_ids.update(path["edge_ids"])
        routes = source.get("candidate_routes")
        candidate_routes = routes if isinstance(routes, Sequence) and not isinstance(routes, str) else ()
        return {
            "original_route_id": original_route_id,
            "target_route_id": target_route_id,
            "original_path": original_path,
            "recommended_path": recommended_path,
            "pickup_path": pickup_path,
            "blocked_edge_ids": blocked_edge_ids,
            "distance_delta_km": cls._number_text(source.get("distance_delta_km")),
            "eta_delta_minutes": cls._integer(source.get("eta_delta_minutes")),
            "visited_node_count": None if recommended_path is None else recommended_path.get("visited_node_count"),
            "routing_status": cls._text(source, "routing_status"),
            "relevant_edges": cls._compact_relevant_edges(
                source.get("road_network_edges"),
                relevant_edge_ids,
            ),
            "network_nodes": cls._compact_network_nodes(source.get("road_network_nodes")),
            "network_edges": cls._compact_network_edges(source.get("road_network_edges")),
            "real_road_route": cls._compact_real_road_route(source.get("real_road_route")),
            "candidate_routes": [cls._compact_route_candidate(route) for route in candidate_routes if isinstance(route, Mapping)],
        }

    @classmethod
    def _compact_real_road_route(cls, value: object) -> dict[str, object] | None:
        if not isinstance(value, Mapping):
            return None
        return {
            "provider": cls._text(value, "provider"),
            "source": cls._text(value, "source"),
            "status": cls._text(value, "status"),
            "coordinate_system": cls._text(value, "coordinate_system"),
            "mapping_version": cls._text(value, "mapping_version"),
            "distance_meters": cls._integer(value.get("distance_meters")),
            "duration_seconds": cls._integer(value.get("duration_seconds")),
            "waypoints": cls._compact_geo_points(value.get("waypoints")),
            "polyline": cls._compact_geo_points(value.get("polyline")),
            "fallback_reason": cls._text(value, "fallback_reason"),
        }

    @classmethod
    def _compact_geo_points(cls, value: object) -> list[dict[str, str | None]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [
            {
                "node_id": cls._text(point, "node_id"),
                "longitude": cls._text(point, "longitude"),
                "latitude": cls._text(point, "latitude"),
            }
            for point in value
            if isinstance(point, Mapping)
        ]

    @classmethod
    def _compact_path(cls, value: object) -> dict[str, object] | None:
        if not isinstance(value, Mapping):
            return None
        return {
            "objective": cls._text(value, "objective"),
            "node_ids": cls._string_list(value.get("node_ids")),
            "edge_ids": cls._string_list(value.get("edge_ids")),
            "distance_km": cls._number_text(value.get("distance_km")),
            "estimated_minutes": cls._integer(value.get("estimated_minutes")),
            "risk_cost": cls._number_text(value.get("risk_cost")),
            "visited_node_count": cls._integer(value.get("visited_node_count")),
            "scoring_formula": cls._text(value, "scoring_formula"),
        }

    @classmethod
    def _compact_route_candidate(
        cls,
        route: Mapping[str, object],
    ) -> dict[str, object]:
        score_components = route.get("score_components")
        components = score_components if isinstance(score_components, Mapping) else {}
        component_keys = (
            "normalized_minutes",
            "normalized_distance",
            "normalized_risk",
            "time_penalty",
            "distance_penalty",
            "risk_penalty",
        )
        return {
            "route_id": cls._text(route, "route_id"),
            "route_name": cls._text(route, "route_name"),
            "objective": cls._text(route, "objective"),
            "node_ids": cls._string_list(route.get("node_ids")),
            "edge_ids": cls._string_list(route.get("edge_ids")),
            "distance_km": cls._number_text(route.get("distance_km")),
            "estimated_minutes": cls._integer(route.get("estimated_minutes")),
            "risk_level": cls._text(route, "risk_level"),
            "risk_cost": cls._number_text(route.get("risk_cost")),
            "visited_node_count": cls._integer(route.get("visited_node_count")),
            "available": route.get("available") if isinstance(route.get("available"), bool) else None,
            "reason": cls._text(route, "reason"),
            "score": cls._number_text(route.get("score")),
            "score_components": {key: cls._number_text(components.get(key)) for key in component_keys if components.get(key) is not None},
            "scoring_formula": cls._text(route, "scoring_formula"),
            "algorithm_version": cls._text(route, "algorithm_version"),
            "road_network_version": cls._integer(route.get("road_network_version")),
        }

    @classmethod
    def _compact_network_nodes(cls, value: object) -> list[dict[str, object]]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [
            {
                "node_id": cls._text(node, "node_id"),
                "name": cls._text(node, "name"),
                "x_km": cls._number_text(node.get("x_km")),
                "y_km": cls._number_text(node.get("y_km")),
                "node_type": cls._text(node, "node_type"),
            }
            for node in value
            if isinstance(node, Mapping)
        ]

    @classmethod
    def _compact_network_edges(cls, value: object) -> list[dict[str, object]]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [
            {
                "edge_id": cls._text(edge, "edge_id"),
                "name": cls._text(edge, "name"),
                "from_node_id": cls._text(edge, "from_node_id"),
                "to_node_id": cls._text(edge, "to_node_id"),
                "distance_km": cls._number_text(edge.get("distance_km")),
                "base_minutes": cls._integer(edge.get("base_minutes")),
                "road_level": cls._text(edge, "road_level"),
                "risk_level": cls._text(edge, "risk_level"),
                "status": cls._text(edge, "status"),
                "congestion_factor": cls._number_text(edge.get("congestion_factor")),
                "weight_limit_tons": cls._number_text(edge.get("weight_limit_tons")),
                "bidirectional": edge.get("bidirectional") is True,
                "version": cls._integer(edge.get("version")),
            }
            for edge in value
            if isinstance(edge, Mapping)
        ]

    @classmethod
    def _compact_relevant_edges(
        cls,
        value: object,
        relevant_edge_ids: set[str],
    ) -> list[dict[str, object]]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [
            {
                "edge_id": edge_id,
                "from_node_id": cls._text(edge, "from_node_id"),
                "to_node_id": cls._text(edge, "to_node_id"),
                "status": cls._text(edge, "status"),
                "bidirectional": edge.get("bidirectional") is True,
            }
            for edge in value
            if isinstance(edge, Mapping) and (edge_id := cls._text(edge, "edge_id")) in relevant_edge_ids
        ]

    @staticmethod
    def _number_text(value: object) -> str | None:
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [item for item in value if isinstance(item, str)]
