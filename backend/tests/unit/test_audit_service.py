import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.audit.service import AuditService
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask


def _service():
    temp = TemporaryDirectory()
    engine = create_engine(f"sqlite+pysqlite:///{Path(temp.name) / 'audit.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        order = Order(order_no="ORD-AUDIT", status="open", origin="A", destination="B")
        s.add(order)
        s.flush()
        task = DispatchTask(task_id="task-001", order_id=order.id, status="done", idempotency_key="audit-key")
        s.add(task)
        s.flush()
        dispatch = Dispatch(
            dispatch_no="DSP-AUDIT", order_id=order.id, task_id=task.id, original_route_id="xinping-road", target_route_id="national-102", status="REROUTED"
        )
        s.add(dispatch)
        s.commit()
    return temp, engine, factory


def _evidence(**overrides):
    value = {
        "task_id": "task-001",
        "decision": "REROUTE",
        "recommended_route": "national-102",
        "memory_adopted": True,
        "adopted_memory_id": "memory-rain-li",
        "memory_results": [{"memory_id": "memory-rain-li"}],
        "fallback_used": False,
        "fallback_reason": None,
        "requires_manual_review": False,
        "error_code": None,
        "analysis_mode": "EIGHT_AGENT_RULE_ASSISTED",
        "identified_issue": "ROAD_HAZARD",
        "issue_subtype": "SLIPPERY",
        "environment_risk": "HIGH",
        "capacity_state": {"capacity_status": "AVAILABLE"},
        "decision_reason": "道路湿滑，需要采用安全路线。",
        "graph_memory_used": True,
        "graph_memory_error": None,
        "graph_memory_facts": [
            {
                "source": {"entity_id": "driver-li"},
                "relation_type": "HAS_RISK_ON",
                "target": {"entity_id": "xinping-road"},
            }
        ],
        "graph_memory_paths": [{"entities": [{"entity_id": "driver-li"}, {"entity_id": "xinping-road"}], "relations": []}],
        "dispatch_result": {"dispatch_id": 1, "target_route_id": "national-102", "executed": True},
    }
    value.update(overrides)
    return value


def test_audit_approves_valid_reroute():
    temp, engine, factory = _service()
    try:
        assert AuditService(factory).audit(_evidence()).audit_status == "APPROVED"
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_detects_route_mismatch():
    temp, engine, factory = _service()
    try:
        assert (
            AuditService(factory).audit(_evidence(dispatch_result={"dispatch_id": 1, "target_route_id": "county-308", "executed": True})).audit_status
            == "REJECTED"
        )
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_requires_review_for_manual_decision():
    temp, engine, factory = _service()
    try:
        assert AuditService(factory).audit(_evidence(decision="MANUAL_REVIEW", requires_manual_review=True)).audit_status == "REVIEW_REQUIRED"
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_requires_review_for_dispatch_version_conflict():
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_evidence(error_code="DISPATCH_VERSION_CONFLICT"))

        assert result.audit_status == "REVIEW_REQUIRED"
        assert result.requires_manual_review is True
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_requires_review_for_vehicle_reservation_conflict():
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_evidence(error_code="VEHICLE_RESERVATION_CONFLICT"))

        assert result.audit_status == "REVIEW_REQUIRED"
        assert result.requires_manual_review is True
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_validates_memory_adoption():
    temp, engine, factory = _service()
    try:
        service = AuditService(factory)
        assert service.audit(_evidence(adopted_memory_id="missing")).audit_status == "REJECTED"
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_validates_fallback_evidence():
    temp, engine, factory = _service()
    try:
        assert AuditService(factory).audit(_evidence(fallback_used=True, fallback_reason=None)).audit_status == "REJECTED"
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_persists_record():
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_evidence())
        with factory() as s:
            record = s.scalar(select(AuditRecord).where(AuditRecord.id == result.audit_record_id))
        assert (record.result, record.dispatch_id) == ("APPROVED", 1)
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_persists_compact_graph_memory_evidence():
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_evidence())
        with factory() as s:
            record = s.scalar(select(AuditRecord).where(AuditRecord.id == result.audit_record_id))
        evidence = json.loads(record.evidence_json)
        assert evidence == {
            "graph_memory_used": True,
            "graph_memory_error": None,
            "facts": ["driver-li|HAS_RISK_ON|xinping-road"],
            "paths": ["driver-li>xinping-road"],
            "analysis_mode": "EIGHT_AGENT_RULE_ASSISTED",
            "identified_issue": "ROAD_HAZARD",
            "issue_subtype": "SLIPPERY",
            "environment_risk": "HIGH",
            "capacity_status": "AVAILABLE",
            "memory_hit_count": 1,
        }
        assert "properties" not in record.evidence_json
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_persists_safe_correlation_id_when_present():
    temp, engine, factory = _service()
    try:
        evidence = _evidence()
        evidence["correlation_id"] = "ops-123"
        result = AuditService(factory).audit(evidence)
        with factory() as s:
            record = s.scalar(select(AuditRecord).where(AuditRecord.id == result.audit_record_id))
        assert json.loads(record.evidence_json)["correlation_id"] == "ops-123"
    finally:
        engine.dispose()
        temp.cleanup()


def _breakdown_evidence(**overrides):
    value = _evidence(
        identified_issue="VEHICLE_BREAKDOWN",
        cargo_weight_kg="700.00",
        cargo_type="COLD_CHAIN",
        vehicle_id="V-001",
        selected_vehicle_id="V-005",
        selected_driver_id="D-003",
        candidate_vehicles=[
            {
                "vehicle_id": "V-005",
                "driver_id": "D-003",
                "vehicle_status": "AVAILABLE",
                "driver_status": "ON_DUTY",
                "eligible": True,
                "remaining_load_kg": "900.00",
                "remaining_capacity_kg": "900.00",
                "cargo_capability": "COLD_CHAIN",
                "score": "93.4",
                "score_components": {
                    "eta_penalty": "9.0",
                    "distance_penalty": "5.60",
                },
                "exclusion_reasons": [],
                "authorization": "must-not-persist",
            }
        ],
        dispatch_result={
            "dispatch_id": 1,
            "target_route_id": "national-102",
            "executed": True,
            "original_vehicle_id": "V-001",
            "target_vehicle_id": "V-005",
            "target_driver_id": "D-003",
        },
    )
    value.update(overrides)
    return value


def _road_block_evidence(**overrides):
    value = _evidence(
        identified_issue="ROAD_BLOCKED",
        blocked_edge_ids=["E04"],
        recommended_path={
            "node_ids": ["N01", "N02", "N07", "N06"],
            "edge_ids": ["E01", "E06", "E09"],
        },
        road_network_edges=[
            {
                "edge_id": "E01",
                "from_node_id": "N01",
                "to_node_id": "N02",
                "bidirectional": True,
                "status": "OPEN",
            },
            {
                "edge_id": "E06",
                "from_node_id": "N02",
                "to_node_id": "N07",
                "bidirectional": True,
                "status": "OPEN",
            },
            {
                "edge_id": "E09",
                "from_node_id": "N07",
                "to_node_id": "N06",
                "bidirectional": True,
                "status": "OPEN",
            },
            {
                "edge_id": "E04",
                "from_node_id": "N04",
                "to_node_id": "N05",
                "bidirectional": True,
                "status": "BLOCKED",
            },
        ],
    )
    value.update(overrides)
    return value


def test_audit_validates_breakdown_vehicle_assignment_capacity_and_cargo() -> None:
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_breakdown_evidence())

        assert result.audit_status == "APPROVED"
        assert result.checks["vehicle_assignment"] is True
        assert result.checks["capacity_constraint"] is True
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_rejects_breakdown_when_target_is_original_or_capacity_is_insufficient() -> None:
    temp, engine, factory = _service()
    try:
        same_vehicle = AuditService(factory).audit(_breakdown_evidence(selected_vehicle_id="V-001"))
        insufficient = AuditService(factory).audit(
            _breakdown_evidence(
                candidate_vehicles=[
                    {
                        "vehicle_id": "V-005",
                        "driver_id": "D-003",
                        "eligible": True,
                        "remaining_load_kg": "600.00",
                        "cargo_capability": "COLD_CHAIN",
                        "score": "93.4",
                        "exclusion_reasons": [],
                    }
                ]
            )
        )

        assert same_vehicle.audit_status == "REJECTED"
        assert same_vehicle.checks["vehicle_assignment"] is False
        assert insufficient.audit_status == "REJECTED"
        assert insufficient.checks["capacity_constraint"] is False
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_validates_road_path_connectivity_and_blocked_edge_exclusion() -> None:
    temp, engine, factory = _service()
    try:
        result = AuditService(factory).audit(_road_block_evidence())

        assert result.audit_status == "APPROVED"
        assert result.checks["route_connectivity"] is True
        assert result.checks["blocked_edge_exclusion"] is True
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_rejects_disconnected_or_blocked_recommended_path() -> None:
    temp, engine, factory = _service()
    try:
        disconnected = AuditService(factory).audit(
            _road_block_evidence(
                recommended_path={
                    "node_ids": ["N01", "N07", "N06"],
                    "edge_ids": ["E01", "E09"],
                }
            )
        )
        blocked = AuditService(factory).audit(
            _road_block_evidence(
                recommended_path={
                    "node_ids": ["N04", "N05"],
                    "edge_ids": ["E04"],
                }
            )
        )

        assert disconnected.audit_status == "REJECTED"
        assert disconnected.checks["route_connectivity"] is False
        assert blocked.audit_status == "REJECTED"
        assert blocked.checks["blocked_edge_exclusion"] is False
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_persists_only_compact_candidate_and_path_evidence() -> None:
    temp, engine, factory = _service()
    try:
        evidence = _breakdown_evidence(
            recommended_path={"node_ids": ["N04", "N06"], "edge_ids": ["E04", "E05"]},
            blocked_edge_ids=["E99"],
        )
        result = AuditService(factory).audit(evidence)
        with factory() as session:
            record = session.get(AuditRecord, result.audit_record_id)
        payload = json.loads(record.evidence_json)

        assert payload["candidate_vehicles"] == [
            {
                "eligible": True,
                "exclusion_reasons": [],
                "score": "93.4",
                "vehicle_id": "V-005",
            }
        ]
        assert payload["recommended_path"] == {
            "edge_ids": ["E04", "E05"],
            "node_ids": ["N04", "N06"],
        }
        assert "authorization" not in record.evidence_json
    finally:
        engine.dispose()
        temp.cleanup()


def _patched_breakdown_candidate(**candidate_patch: object) -> dict[str, object]:
    evidence = _breakdown_evidence()
    candidates = evidence["candidate_vehicles"]
    assert isinstance(candidates, list) and isinstance(candidates[0], dict)
    candidates[0].update(candidate_patch)
    return evidence


@pytest.mark.parametrize(
    ("candidate_patch", "evidence_patch"),
    [
        ({"vehicle_status": "RESERVED"}, {}),
        ({"driver_status": "OFF_DUTY"}, {}),
        ({"exclusion_reasons": ["VEHICLE_UNAVAILABLE"]}, {}),
        ({"driver_id": "D-999"}, {}),
        ({}, {"selected_driver_id": "D-999"}),
    ],
)
def test_audit_rejects_forged_eligible_vehicle_or_driver(
    candidate_patch: dict[str, object],
    evidence_patch: dict[str, object],
) -> None:
    temp, engine, factory = _service()
    try:
        evidence = _patched_breakdown_candidate(**candidate_patch)
        evidence.update(evidence_patch)

        result = AuditService(factory).audit(evidence)

        assert result.audit_status == "REJECTED"
        assert result.checks["vehicle_assignment"] is False
    finally:
        engine.dispose()
        temp.cleanup()


def test_audit_rejects_path_edge_marked_blocked_even_when_declaration_omits_it() -> None:
    temp, engine, factory = _service()
    try:
        evidence = _road_block_evidence()
        road_edges = evidence["road_network_edges"]
        assert isinstance(road_edges, list) and isinstance(road_edges[1], dict)
        road_edges[1]["status"] = "BLOCKED"

        result = AuditService(factory).audit(evidence)

        assert result.audit_status == "REJECTED"
        assert result.checks["blocked_edge_exclusion"] is False
    finally:
        engine.dispose()
        temp.cleanup()
