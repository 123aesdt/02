import json
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.audit.models import AuditChecks, AuditResult
from app.models.audit import AuditRecord
from app.models.task import DispatchTask
from app.observability.context import safe_correlation_id


class AuditPersistenceError(Exception):
    """Raised when an audit result cannot be durably recorded."""


class AuditService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def audit(self, evidence: Mapping[str, object]) -> AuditResult:
        dispatch = self._mapping(evidence.get("dispatch_result"))
        decision = self._text(evidence.get("decision"))
        dispatch_id = self._integer(dispatch.get("dispatch_id"))
        executed = dispatch.get("executed") is True
        target_route_id = self._text(dispatch.get("target_route_id"))
        checks: AuditChecks = {
            "route_consistency": True,
            "memory_consistency": True,
            "fallback_consistency": True,
            "dispatch_execution": executed,
            "vehicle_assignment": True,
            "capacity_constraint": True,
            "route_connectivity": True,
            "blocked_edge_exclusion": True,
        }

        status, reason, requires_manual_review = self._evaluate(
            evidence=evidence,
            decision=decision,
            executed=executed,
            target_route_id=target_route_id,
            checks=checks,
        )
        record_id = self._persist_if_possible(
            task_id=self._text(evidence.get("task_id")),
            dispatch_id=dispatch_id,
            status=status,
            reason=reason,
            evidence_json=json.dumps(self._graph_evidence(evidence), ensure_ascii=False, sort_keys=True),
        )
        return AuditResult(
            audit_status=status,
            passed=status == "APPROVED",
            reason=reason,
            checks=checks,
            dispatch_id=dispatch_id,
            requires_manual_review=requires_manual_review,
            audit_record_id=record_id,
        )

    def _evaluate(
        self,
        *,
        evidence: Mapping[str, object],
        decision: str | None,
        executed: bool,
        target_route_id: str | None,
        checks: AuditChecks,
    ) -> tuple[str, str, bool]:
        if (
            decision == "MANUAL_REVIEW"
            or evidence.get("requires_manual_review") is True
            or self._text(evidence.get("error_code"))
            in {
                "DISPATCH_CONFLICT",
                "DISPATCH_VERSION_CONFLICT",
                "VEHICLE_RESERVATION_CONFLICT",
            }
        ):
            return "REVIEW_REQUIRED", "Dispatch requires manual review.", True

        issue = self._text(evidence.get("identified_issue")) or self._text(evidence.get("anomaly_type"))
        if issue == "VEHICLE_BREAKDOWN":
            dispatch = self._mapping(evidence.get("dispatch_result"))
            original_vehicle_id = self._text(dispatch.get("original_vehicle_id")) or self._text(evidence.get("vehicle_id"))
            target_vehicle_id = self._text(dispatch.get("target_vehicle_id"))
            target_driver_id = self._text(dispatch.get("target_driver_id"))
            selected_vehicle_id = self._text(evidence.get("selected_vehicle_id"))
            selected_driver_id = self._text(evidence.get("selected_driver_id"))
            candidate = self._candidate(
                evidence.get("candidate_vehicles"),
                target_vehicle_id,
            )
            candidate_vehicle_id = self._text(candidate.get("vehicle_id"))
            candidate_driver_id = self._text(candidate.get("driver_id"))
            exclusion_reasons = candidate.get("exclusion_reasons")
            has_no_exclusions = isinstance(exclusion_reasons, Sequence) and not isinstance(exclusion_reasons, str) and not exclusion_reasons
            checks["vehicle_assignment"] = (
                original_vehicle_id is not None
                and target_vehicle_id is not None
                and target_vehicle_id != original_vehicle_id
                and candidate_vehicle_id == selected_vehicle_id == target_vehicle_id
                and candidate_driver_id == selected_driver_id == target_driver_id
                and candidate.get("vehicle_status") == "AVAILABLE"
                and candidate.get("driver_status") in {"ON_DUTY", "AVAILABLE"}
                and candidate.get("eligible") is True
                and has_no_exclusions
            )
            cargo_weight = self._decimal(evidence.get("cargo_weight_kg"))
            remaining_capacity = self._decimal(
                candidate.get("remaining_capacity_kg") if candidate.get("remaining_capacity_kg") is not None else candidate.get("remaining_load_kg")
            )
            cargo_type = self._text(evidence.get("cargo_type"))
            cargo_capability = self._text(candidate.get("cargo_capability"))
            checks["capacity_constraint"] = (
                cargo_weight is not None
                and remaining_capacity is not None
                and remaining_capacity >= cargo_weight
                and (cargo_type != "COLD_CHAIN" or cargo_capability == "COLD_CHAIN")
            )
            if not checks["vehicle_assignment"]:
                return (
                    "REJECTED",
                    "Replacement vehicle assignment is inconsistent.",
                    True,
                )
            if not checks["capacity_constraint"]:
                return (
                    "REJECTED",
                    "Replacement vehicle capacity or cargo capability is invalid.",
                    True,
                )

        blocked_edge_ids = self._string_list(evidence.get("blocked_edge_ids"))
        if issue == "ROAD_BLOCKED" or blocked_edge_ids:
            recommended_path = self._mapping(evidence.get("recommended_path"))
            path_edge_ids = self._string_list(recommended_path.get("edge_ids"))
            path_node_ids = self._string_list(recommended_path.get("node_ids"))
            road_edges = evidence.get("road_network_edges")
            checks["route_connectivity"] = self._path_connects(
                path_node_ids,
                path_edge_ids,
                road_edges,
            )
            checks["blocked_edge_exclusion"] = set(path_edge_ids).isdisjoint(blocked_edge_ids) and self._path_edges_are_open(path_edge_ids, road_edges)
            if not checks["route_connectivity"]:
                return (
                    "REJECTED",
                    "Recommended path is not connected in the road network.",
                    True,
                )
            if not checks["blocked_edge_exclusion"]:
                return "REJECTED", "Recommended path includes a blocked edge.", True
        if decision == "NO_SAFE_ROUTE" and executed:
            checks["route_consistency"] = False
            return "REJECTED", "No-safe-route decision cannot execute a dispatch.", True

        if decision == "REROUTE":
            recommended_route = self._text(evidence.get("recommended_route"))
            checks["route_consistency"] = recommended_route is not None and executed and target_route_id == recommended_route
            if not checks["route_consistency"]:
                return (
                    "REJECTED",
                    "Recommended route and dispatch target do not match.",
                    True,
                )

        if decision == "KEEP_ROUTE":
            original_route = self._text(evidence.get("route_id"))
            checks["route_consistency"] = executed and target_route_id == original_route
            if not checks["route_consistency"]:
                return (
                    "REJECTED",
                    "Keep-route dispatch target does not match the original route.",
                    True,
                )

        if evidence.get("memory_adopted") is True:
            adopted_memory_id = self._text(evidence.get("adopted_memory_id"))
            checks["memory_consistency"] = adopted_memory_id is not None and self._has_memory(
                evidence.get("memory_results"),
                adopted_memory_id,
            )
            if not checks["memory_consistency"]:
                return (
                    "REJECTED",
                    "Adopted memory is absent from recalled memory results.",
                    True,
                )

        if evidence.get("fallback_used") is True:
            checks["fallback_consistency"] = bool(self._text(evidence.get("fallback_reason")))
            if not checks["fallback_consistency"]:
                return (
                    "REJECTED",
                    "Fallback dispatch requires a fallback reason.",
                    True,
                )

        return "APPROVED", "Audit checks passed.", False

    def _persist_if_possible(
        self,
        *,
        task_id: str | None,
        dispatch_id: int | None,
        status: str,
        reason: str,
        evidence_json: str,
    ) -> int | None:
        if task_id is None or dispatch_id is None:
            return None
        try:
            with self._session_factory() as session:
                task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
                if task is None:
                    raise AuditPersistenceError("Audit task was not found.")
                existing = session.scalar(
                    select(AuditRecord).where(
                        AuditRecord.task_id == task.id,
                        AuditRecord.dispatch_id == dispatch_id,
                    )
                )
                if existing is not None:
                    return existing.id
                record = AuditRecord(
                    task_id=task.id,
                    dispatch_id=dispatch_id,
                    result=status,
                    reason=reason,
                    evidence_json=evidence_json,
                )
                session.add(record)
                session.commit()
                return record.id
        except AuditPersistenceError:
            raise
        except SQLAlchemyError as error:
            raise AuditPersistenceError("Audit record persistence failed.") from error

    @staticmethod
    def _mapping(value: object) -> Mapping[str, object]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _text(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _integer(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _has_memory(value: object, memory_id: str) -> bool:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return False
        return any(isinstance(item, Mapping) and item.get("memory_id") == memory_id for item in value)

    @classmethod
    def _graph_evidence(cls, evidence: Mapping[str, object]) -> dict[str, object]:
        facts: list[str] = []
        fact_values = evidence.get("graph_memory_facts")
        if isinstance(fact_values, Sequence) and not isinstance(fact_values, str):
            for value in fact_values[:10]:
                if not isinstance(value, Mapping):
                    continue
                source = cls._entity_id(value.get("source"))
                target = cls._entity_id(value.get("target"))
                relation = cls._text(value.get("relation_type"))
                if source and relation and target:
                    facts.append(f"{source}|{relation}|{target}")

        paths: list[str] = []
        path_values = evidence.get("graph_memory_paths")
        if isinstance(path_values, Sequence) and not isinstance(path_values, str):
            for value in path_values[:5]:
                if not isinstance(value, Mapping):
                    continue
                entities = value.get("entities")
                if not isinstance(entities, Sequence) or isinstance(entities, str):
                    continue
                ids = [entity_id for item in entities if (entity_id := cls._entity_id(item))]
                if ids:
                    paths.append(">".join(ids))
        memory_values = evidence.get("memory_results")
        memory_hit_count = min(len(memory_values), 10) if isinstance(memory_values, Sequence) and not isinstance(memory_values, str) else 0
        capacity = cls._mapping(evidence.get("capacity_state"))
        compact: dict[str, object] = {
            "graph_memory_used": evidence.get("graph_memory_used") is True,
            "graph_memory_error": cls._text(evidence.get("graph_memory_error")),
            "facts": facts,
            "paths": paths,
            "analysis_mode": cls._text(evidence.get("analysis_mode")),
            "identified_issue": cls._text(evidence.get("identified_issue")),
            "issue_subtype": cls._text(evidence.get("issue_subtype")),
            "environment_risk": cls._text(evidence.get("environment_risk")),
            "capacity_status": cls._text(capacity.get("capacity_status")),
            "memory_hit_count": memory_hit_count,
        }
        candidate_values = evidence.get("candidate_vehicles")
        candidates = candidate_values[:20] if isinstance(candidate_values, Sequence) and not isinstance(candidate_values, str) else ()
        if "candidate_vehicles" in evidence:
            compact["candidate_vehicles"] = [
                {
                    "vehicle_id": cls._text(item.get("vehicle_id")),
                    "score": cls._number_text(item.get("score")),
                    "eligible": item.get("eligible") is True,
                    "exclusion_reasons": cls._string_list(item.get("exclusion_reasons")),
                }
                for item in candidates
                if isinstance(item, Mapping)
            ]

        extended_keys = {
            "candidate_vehicles",
            "cargo_weight_kg",
            "cargo_type",
            "road_network_edges",
            "original_path",
            "pickup_route",
        }
        if any(key in evidence for key in extended_keys):
            dispatch = cls._mapping(evidence.get("dispatch_result"))
            target_vehicle_id = cls._text(dispatch.get("target_vehicle_id"))
            if target_vehicle_id is None:
                target_vehicle_id = cls._text(evidence.get("selected_vehicle_id"))
            selected_candidate = next(
                (item for item in candidates if isinstance(item, Mapping) and cls._text(item.get("vehicle_id")) == target_vehicle_id),
                None,
            )
            compact.update(
                {
                    "task_id": cls._text(evidence.get("task_id")),
                    "decision": cls._text(evidence.get("decision")),
                    "route_id": cls._text(evidence.get("route_id")),
                    "recommended_route": cls._text(evidence.get("recommended_route")),
                    "anomaly_type": cls._text(evidence.get("anomaly_type")),
                    "vehicle_id": cls._text(evidence.get("vehicle_id")),
                    "selected_vehicle_id": cls._text(evidence.get("selected_vehicle_id")),
                    "selected_driver_id": cls._text(evidence.get("selected_driver_id")),
                    "cargo_weight_kg": cls._number_text(evidence.get("cargo_weight_kg")),
                    "cargo_type": cls._text(evidence.get("cargo_type")),
                    "fallback_used": evidence.get("fallback_used") is True,
                    "fallback_reason": cls._text(evidence.get("fallback_reason")),
                    "memory_adopted": evidence.get("memory_adopted") is True,
                    "adopted_memory_id": cls._text(evidence.get("adopted_memory_id")),
                    "requires_manual_review": (evidence.get("requires_manual_review") is True),
                    "error_code": cls._text(evidence.get("error_code")),
                    "dispatch_result": {
                        key: dispatch.get(key)
                        for key in (
                            "dispatch_id",
                            "target_route_id",
                            "executed",
                            "original_vehicle_id",
                            "target_vehicle_id",
                            "target_driver_id",
                        )
                        if key in dispatch
                    },
                    "selected_candidate": (cls._compact_selected_candidate(selected_candidate) if selected_candidate is not None else None),
                }
            )

        path_sources = (
            ("original_path", evidence.get("original_path")),
            ("recommended_path", evidence.get("recommended_path")),
            (
                "pickup_path",
                evidence.get("pickup_path") if evidence.get("pickup_path") is not None else evidence.get("pickup_route"),
            ),
        )
        relevant_edge_ids: set[str] = set()
        for key, value in path_sources:
            if value is None and key not in evidence:
                continue
            path = cls._compact_path(value)
            compact[key] = path
            relevant_edge_ids.update(path["edge_ids"])
        if "blocked_edge_ids" in evidence:
            blocked_edge_ids = cls._string_list(evidence.get("blocked_edge_ids"))
            compact["blocked_edge_ids"] = blocked_edge_ids
            relevant_edge_ids.update(blocked_edge_ids)
        if "road_network_edges" in evidence:
            compact["road_network_edges"] = cls._compact_relevant_edges(
                evidence.get("road_network_edges"),
                relevant_edge_ids,
            )

        correlation_id = safe_correlation_id(evidence.get("correlation_id"))
        if correlation_id is not None:
            compact["correlation_id"] = correlation_id
        return compact

    @classmethod
    def _compact_selected_candidate(
        cls,
        candidate: Mapping[str, object],
    ) -> dict[str, object]:
        remaining_capacity = candidate.get("remaining_capacity_kg")
        if remaining_capacity is None:
            remaining_capacity = candidate.get("remaining_load_kg")
        score_components = cls._mapping(candidate.get("score_components"))
        allowed_component_keys = (
            "eta_penalty",
            "distance_penalty",
            "load_penalty",
            "road_risk_penalty",
            "same_station_bonus",
            "cargo_exact_match_bonus",
        )
        return {
            "vehicle_id": cls._text(candidate.get("vehicle_id")),
            "driver_id": cls._text(candidate.get("driver_id")),
            "vehicle_status": cls._text(candidate.get("vehicle_status")),
            "driver_status": cls._text(candidate.get("driver_status")),
            "remaining_capacity_kg": cls._number_text(remaining_capacity),
            "cargo_capability": cls._text(candidate.get("cargo_capability")),
            "score": cls._number_text(candidate.get("score")),
            "score_components": {key: cls._number_text(score_components.get(key)) for key in allowed_component_keys if score_components.get(key) is not None},
            "eligible": candidate.get("eligible") is True,
            "exclusion_reasons": cls._string_list(candidate.get("exclusion_reasons")),
        }

    @classmethod
    def _compact_path(cls, value: object) -> dict[str, list[str]]:
        path = cls._mapping(value)
        return {
            "node_ids": cls._string_list(path.get("node_ids")),
            "edge_ids": cls._string_list(path.get("edge_ids")),
        }

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
                "from_node_id": cls._text(edge.get("from_node_id")),
                "to_node_id": cls._text(edge.get("to_node_id")),
                "status": cls._text(edge.get("status")),
                "bidirectional": edge.get("bidirectional") is True,
            }
            for edge in value
            if isinstance(edge, Mapping) and (edge_id := cls._text(edge.get("edge_id"))) in relevant_edge_ids
        ]

    @staticmethod
    def _number_text(value: object) -> str | None:
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    @classmethod
    def _candidate(
        cls,
        value: object,
        vehicle_id: str | None,
    ) -> Mapping[str, object]:
        if vehicle_id is None or not isinstance(value, Sequence) or isinstance(value, str):
            return {}
        return next(
            (item for item in value if isinstance(item, Mapping) and cls._text(item.get("vehicle_id")) == vehicle_id),
            {},
        )

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        try:
            return Decimal(str(value)) if value is not None else None
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(value, str):
            return []
        return [item for item in value if isinstance(item, str)]

    @classmethod
    def _path_connects(
        cls,
        node_ids: list[str],
        edge_ids: list[str],
        road_edges: object,
    ) -> bool:
        if not edge_ids or len(node_ids) != len(edge_ids) + 1:
            return False
        edges = cls._road_edges_by_id(road_edges)
        for index, edge_id in enumerate(edge_ids):
            edge = edges.get(edge_id)
            if edge is None:
                return False
            start = cls._text(edge.get("from_node_id"))
            end = cls._text(edge.get("to_node_id"))
            path_start, path_end = node_ids[index], node_ids[index + 1]
            forward = (start, end) == (path_start, path_end)
            reverse = edge.get("bidirectional") is True and (end, start) == (
                path_start,
                path_end,
            )
            if not forward and not reverse:
                return False
        return True

    @classmethod
    def _path_edges_are_open(
        cls,
        edge_ids: list[str],
        road_edges: object,
    ) -> bool:
        edges = cls._road_edges_by_id(road_edges)
        return bool(edge_ids) and all(edge_id in edges and edges[edge_id].get("status") == "OPEN" for edge_id in edge_ids)

    @classmethod
    def _road_edges_by_id(
        cls,
        road_edges: object,
    ) -> dict[str, Mapping[str, object]]:
        if not isinstance(road_edges, Sequence) or isinstance(road_edges, str):
            return {}
        return {edge_id: item for item in road_edges if isinstance(item, Mapping) and (edge_id := cls._text(item.get("edge_id"))) is not None}

    @staticmethod
    def _entity_id(value: object) -> str | None:
        return value.get("entity_id") if isinstance(value, Mapping) and isinstance(value.get("entity_id"), str) else None
