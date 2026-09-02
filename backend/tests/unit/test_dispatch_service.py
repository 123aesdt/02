from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.agents.dispatch import dispatch_node
from app.audit.service import AuditService
from app.dispatch.models import DispatchResult
from app.dispatch.service import DispatchService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.order import Order
from app.models.task import DispatchTask


def _service():
    temp = TemporaryDirectory()
    engine = create_engine(f"sqlite+pysqlite:///{Path(temp.name) / 'dispatch.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        order = Order(order_no="ORD-DISPATCH", status="open", origin="A", destination="B")
        session.add(order)
        session.flush()
        session.add(DispatchTask(task_id="task-001", order_id=order.id, status="created", idempotency_key="key-001"))
        session.commit()
    return temp, engine, factory


def test_dispatch_service_creates_dispatch():
    temp, engine, factory = _service()
    try:
        result = DispatchService(factory).execute("task-001", 1, "xinping-road", "national-102", "REROUTE", "safer", False, None, False)
        assert result.executed is True
        assert result.target_route_id == "national-102"
    finally:
        engine.dispose()
        temp.cleanup()


def test_dispatch_service_persists_reroute():
    temp, engine, factory = _service()
    try:
        result = DispatchService(factory).execute("task-001", 1, "xinping-road", "national-102", "REROUTE", "safer", True, "timeout", False)
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.id == result.dispatch_id))
        assert (dispatch.original_route_id, dispatch.target_route_id, dispatch.fallback_used) == ("xinping-road", "national-102", True)
    finally:
        engine.dispose()
        temp.cleanup()


def test_dispatch_service_persists_one_manual_review_draft():
    temp, engine, factory = _service()
    try:
        service = DispatchService(factory)
        first = service.execute(
            "task-001",
            1,
            "xinping-road",
            None,
            "MANUAL_REVIEW",
            "轮胎故障且车辆无法继续执行。",
            False,
            None,
            True,
            recommended_action="立即安全停车并更换轮胎。",
            analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
            issue_subtype="TIRE",
        )
        second = service.execute(
            "task-001",
            1,
            "xinping-road",
            None,
            "MANUAL_REVIEW",
            "轮胎故障且车辆无法继续执行。",
            False,
            None,
            True,
            recommended_action="立即安全停车并更换轮胎。",
            analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
            issue_subtype="TIRE",
        )
        with factory() as session:
            dispatches = list(session.scalars(select(Dispatch)))
        assert first.dispatch_id == second.dispatch_id == dispatches[0].id
        assert first.status == "REVIEW_REQUIRED"
        assert first.executed is False
        assert first.target_route_id is None
        assert len(dispatches) == 1
        assert dispatches[0].recommended_action == "立即安全停车并更换轮胎。"
        assert dispatches[0].analysis_mode == "EIGHT_AGENT_RULE_ASSISTED"
        assert dispatches[0].issue_subtype == "TIRE"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_dispatch_agent_writes_state():
    class Service:
        def execute(self, *args):
            return DispatchResult(1, "DSP-1", 1, "task-001", "REROUTED", "xinping-road", "national-102", 1, True, "safer", False)

    state = {
        "task_id": "task-001",
        "order_id": 1,
        "route_id": "xinping-road",
        "recommended_route": "national-102",
        "decision": "REROUTE",
        "decision_reason": "safer",
        "fallback_used": False,
        "fallback_reason": None,
        "requires_manual_review": False,
    }
    patch = await dispatch_node(state, Service())

    assert patch["dispatch_result"]["target_route_id"] == "national-102"
    assert patch["dispatch_result"]["executed"] is True


@pytest.mark.asyncio
async def test_graph_routes_and_dispatches():
    from tests.graph.test_routing_agent import _capacity_service, _environment_service, _memory_service, _routing_service

    temp, engine, factory = _service()
    try:
        graph = build_graph(
            GraphDependencies(
                entity_memory_service=await _memory_service(),
                environment_service=_environment_service(),
                capacity_service=_capacity_service(),
                routing_service=_routing_service(),
                dispatch_service=DispatchService(factory),
            )
        )
        result = await graph.ainvoke(
            {
                "task_id": "task-001",
                "order_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            }
        )
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.id == result["dispatch_result"]["dispatch_id"]))
        assert result["recommended_route"] == "national-102"
        assert result["dispatch_result"]["executed"] is True
        assert dispatch.target_route_id == "national-102"
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_graph_runs_audit_after_dispatch():
    from tests.graph.test_routing_agent import (
        _capacity_service,
        _environment_service,
        _memory_service,
        _routing_service,
    )

    temp, engine, factory = _service()
    try:
        graph = build_graph(
            GraphDependencies(
                entity_memory_service=await _memory_service(),
                environment_service=_environment_service(),
                capacity_service=_capacity_service(),
                routing_service=_routing_service(),
                dispatch_service=DispatchService(factory),
                audit_service=AuditService(factory),
            )
        )
        result = await graph.ainvoke(
            {
                "task_id": "task-001",
                "order_id": 1,
                "driver_id": "driver-li",
                "vehicle_id": "vehicle-001",
                "route_id": "xinping-road",
                "anomaly_type": "rain_slippery",
                "anomaly_description": "李师傅在雨天经过新平路，道路出现湿滑风险。",
            }
        )
        with factory() as session:
            dispatch = session.scalar(select(Dispatch).where(Dispatch.id == result["dispatch_result"]["dispatch_id"]))
            audit = session.scalar(select(AuditRecord).where(AuditRecord.id == result["audit_result"]["audit_record_id"]))

        assert result["normalized_anomaly"]
        assert result["memory_results"][0]["memory_id"] == "memory-rain-li"
        assert result["recommended_route"] == "national-102"
        assert result["dispatch_result"]["executed"] is True
        assert result["dispatch_result"]["target_route_id"] == "national-102"
        assert result["audit_result"]["audit_status"] == "APPROVED"
        assert result["audit_result"]["passed"] is True
        assert dispatch.target_route_id == "national-102"
        assert (audit.task_id, audit.dispatch_id, audit.result) == (
            1,
            dispatch.id,
            "APPROVED",
        )
    finally:
        engine.dispose()
        temp.cleanup()
