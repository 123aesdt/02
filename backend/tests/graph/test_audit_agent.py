import pytest

from app.agents.audit import audit_node
from app.audit.models import AuditResult
from app.audit.service import AuditPersistenceError


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "task_id": "task-001",
        "order_id": 1,
        "driver_id": "driver-li",
        "vehicle_id": "vehicle-001",
        "route_id": "xinping-road",
        "anomaly_type": "rain_slippery",
        "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
        "memory_results": [{"memory_id": "memory-rain-li"}],
        "memory_adopted": True,
        "adopted_memory_id": "memory-rain-li",
        "fallback_used": False,
        "fallback_reason": None,
        "recommended_route": "national-102",
        "decision": "REROUTE",
        "decision_reason": "Historical memory selects a safer route.",
        "dispatch_result": {
            "dispatch_id": 1,
            "dispatch_no": "DSP-1",
            "status": "REROUTED",
            "target_route_id": "national-102",
            "version": 1,
            "executed": True,
        },
        "requires_manual_review": False,
        "error_code": None,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_audit_agent_approves_valid_dispatch():
    class Service:
        def audit(self, evidence: object) -> AuditResult:
            assert isinstance(evidence, dict)
            assert evidence["graph_memory_used"] is True
            assert evidence["graph_memory_error"] is None
            assert evidence["graph_memory_facts"][0]["relation_type"] == "HAS_RISK_ON"
            return AuditResult(
                "APPROVED",
                True,
                "Audit checks passed.",
                {
                    "route_consistency": True,
                    "memory_consistency": True,
                    "fallback_consistency": True,
                    "dispatch_execution": True,
                },
                1,
                False,
                10,
            )

    patch = await audit_node(
        _state(
            graph_memory_used=True,
            graph_memory_error=None,
            graph_memory_facts=[
                {
                    "source": {"entity_id": "driver-li"},
                    "relation_type": "HAS_RISK_ON",
                    "target": {"entity_id": "xinping-road"},
                }
            ],
            graph_memory_paths=[],
        ),
        Service(),
    )

    assert patch["audit_result"]["audit_status"] == "APPROVED"
    assert patch["audit_result"]["passed"] is True
    assert patch["requires_manual_review"] is False


@pytest.mark.asyncio
async def test_audit_agent_marks_manual_review():
    class Service:
        def audit(self, evidence: object) -> AuditResult:
            return AuditResult(
                "REVIEW_REQUIRED",
                False,
                "Dispatch requires manual review.",
                {
                    "route_consistency": True,
                    "memory_consistency": True,
                    "fallback_consistency": True,
                    "dispatch_execution": False,
                },
                None,
                True,
                None,
            )

    patch = await audit_node(
        _state(
            decision="MANUAL_REVIEW",
            requires_manual_review=True,
            error_code="DISPATCH_VERSION_CONFLICT",
        ),
        Service(),
    )

    assert patch["audit_result"]["audit_status"] == "REVIEW_REQUIRED"
    assert patch["requires_manual_review"] is True


@pytest.mark.asyncio
async def test_audit_agent_handles_persistence_failure():
    class Service:
        def audit(self, evidence: object) -> AuditResult:
            raise AuditPersistenceError("database details must not enter state")

    patch = await audit_node(_state(), Service())

    assert patch == {
        "requires_manual_review": True,
        "error_code": "AUDIT_PERSISTENCE_ERROR",
        "error_message": "Audit result could not be persisted.",
        "audit_result": None,
    }
