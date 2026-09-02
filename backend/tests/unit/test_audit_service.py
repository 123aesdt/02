import json
from pathlib import Path
from tempfile import TemporaryDirectory

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
        "graph_memory_paths": [
            {"entities": [{"entity_id": "driver-li"}, {"entity_id": "xinping-road"}], "relations": []}
        ],
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
