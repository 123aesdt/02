from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.dispatch.service as dispatch_service_module
from app.agents.dispatch import dispatch_node
from app.audit.service import AuditService
from app.dispatch.models import DispatchResult
from app.dispatch.service import DispatchService, VehicleReservationConflict
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.models.audit import AuditRecord
from app.models.base import Base
from app.models.dispatch import Dispatch
from app.models.dispatch_evidence import DispatchEvidence
from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadNode
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
        def execute(self, *args, **kwargs):
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


def _breakdown_execution_args(task_id: str = "task-001") -> dict[str, object]:
    candidates = [
        {
            "vehicle_id": "V-005",
            "driver_id": "D-003",
            "eligible": True,
            "vehicle_status": "AVAILABLE",
            "remaining_load_kg": "900.00",
            "cargo_capability": "COLD_CHAIN",
            "score": "93.4",
            "exclusion_reasons": [],
        }
    ]
    return {
        "task_id": task_id,
        "order_id": 1,
        "original_route_id": "RTE-ORIGINAL",
        "target_route_id": "RTE-RECOMMENDED",
        "decision": "REROUTE",
        "decision_reason": "替代车辆与路线均满足约束。",
        "fallback_used": False,
        "fallback_reason": None,
        "requires_manual_review": False,
        "original_vehicle_id": "V-001",
        "candidate_vehicles": candidates,
        "transfer_node_id": "N04",
        "fleet_evidence": {"algorithm_version": "FLEET_SCORE_V1", "candidates": candidates},
        "route_evidence": {
            "algorithm_version": "DIJKSTRA_V1",
            "road_network_version": 7,
            "recommended_path": {"node_ids": ["N04", "N06"], "edge_ids": ["E04", "E05"]},
        },
    }


def _seed_breakdown_vehicle(factory) -> None:
    with factory() as session:
        session.add_all(
            [
                RoadNode(node_id="N04", name="故障点", x_km=5, y_km=2, node_type="INCIDENT_POINT"),
                RoadNode(node_id="N15", name="维修站", x_km=4, y_km=1, node_type="STATION"),
                FleetDriver(
                    driver_id="D-003",
                    name="陈师傅",
                    license_class="C1",
                    status="ON_DUTY",
                    current_vehicle_id="V-005",
                    current_node_id="N15",
                ),
                FleetVehicle(
                    vehicle_id="V-005",
                    plate_no="新物冷链-05",
                    vehicle_type="REFRIGERATED_VAN",
                    max_load_kg=1000,
                    current_load_kg=100,
                    cargo_capability="COLD_CHAIN",
                    gross_weight_tons="2.40",
                    status="AVAILABLE",
                    current_node_id="N15",
                    assigned_driver_id="D-003",
                ),
            ]
        )
        session.commit()


def test_dispatch_reserves_replacement_and_persists_two_evidence_rows() -> None:
    temp, engine, factory = _service()
    try:
        _seed_breakdown_vehicle(factory)

        result = DispatchService(factory).execute(**_breakdown_execution_args())

        with factory() as session:
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-005"))
            dispatch = session.get(Dispatch, result.dispatch_id)
            evidence = session.scalars(select(DispatchEvidence).where(DispatchEvidence.dispatch_id == dispatch.id)).all()
        assert (vehicle.status, dispatch.original_vehicle_id, dispatch.target_vehicle_id) == (
            "RESERVED",
            "V-001",
            "V-005",
        )
        assert dispatch.target_driver_id == "D-003"
        assert dispatch.transfer_node_id == "N04"
        assert result.target_driver_id == "D-003"
        assert {item.evidence_type for item in evidence} == {
            "FLEET_ALLOCATION",
            "ROUTE_CALCULATION",
        }
        assert len(evidence) == 2
    finally:
        engine.dispose()
        temp.cleanup()


def test_dispatch_task_replay_returns_persisted_assignment_without_duplicate_side_effects() -> None:
    temp, engine, factory = _service()
    try:
        _seed_breakdown_vehicle(factory)
        service = DispatchService(factory)

        first = service.execute(**_breakdown_execution_args())
        replay = service.execute(**_breakdown_execution_args())

        with factory() as session:
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == "V-005"))
            evidence_count = len(session.scalars(select(DispatchEvidence).where(DispatchEvidence.dispatch_id == first.dispatch_id)).all())
            dispatch_count = len(session.scalars(select(Dispatch)).all())
        assert replay == first
        assert (vehicle.status, vehicle.version) == ("RESERVED", 2)
        assert evidence_count == 2
        assert dispatch_count == 1
    finally:
        engine.dispose()
        temp.cleanup()


@pytest.mark.asyncio
async def test_dispatch_agent_converts_vehicle_reservation_conflict_to_review() -> None:
    class ConflictingService:
        def execute(self, *args, **kwargs):
            raise VehicleReservationConflict

    patch = await dispatch_node(
        {
            "task_id": "task-001",
            "order_id": 1,
            "route_id": "RTE-ORIGINAL",
            "recommended_route": "RTE-TARGET",
            "decision": "REROUTE",
            "decision_reason": "车辆发生并发预占。",
            "fallback_used": False,
            "requires_manual_review": False,
            "vehicle_id": "V-001",
            "candidate_vehicles": [],
            "incident_node_id": "N04",
        },
        ConflictingService(),
    )

    assert patch == {
        "requires_manual_review": True,
        "error_code": "VEHICLE_RESERVATION_CONFLICT",
        "error_message": "Replacement vehicle reservation conflicted with another dispatch.",
    }


def _seed_second_breakdown_vehicle(factory) -> None:
    with factory() as session:
        session.add_all(
            [
                FleetDriver(
                    driver_id="D-004",
                    name="王师傅",
                    license_class="C1",
                    status="ON_DUTY",
                    current_vehicle_id="V-006",
                    current_node_id="N15",
                ),
                FleetVehicle(
                    vehicle_id="V-006",
                    plate_no="新物冷链-06",
                    vehicle_type="REFRIGERATED_VAN",
                    max_load_kg=1000,
                    current_load_kg=100,
                    cargo_capability="COLD_CHAIN",
                    gross_weight_tons="2.40",
                    status="AVAILABLE",
                    current_node_id="N15",
                    assigned_driver_id="D-004",
                ),
            ]
        )
        session.commit()


def test_dispatch_preserves_the_supplied_eligible_candidate_order() -> None:
    temp, engine, factory = _service()
    try:
        _seed_breakdown_vehicle(factory)
        _seed_second_breakdown_vehicle(factory)
        args = _breakdown_execution_args()
        args["candidate_vehicles"] = [
            {
                "vehicle_id": "V-006",
                "driver_id": "D-004",
                "eligible": True,
                "score": "90.0",
                "exclusion_reasons": [],
            },
            {
                "vehicle_id": "V-005",
                "driver_id": "D-003",
                "eligible": True,
                "score": "93.4",
                "exclusion_reasons": [],
            },
        ]

        result = DispatchService(factory).execute(**args)

        assert (result.target_vehicle_id, result.target_driver_id) == (
            "V-006",
            "D-004",
        )
    finally:
        engine.dispose()
        temp.cleanup()


def test_dispatch_service_reraises_unrelated_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temp, engine, factory = _service()
    try:
        with factory() as session:
            first_task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == "task-001"))
            session.add(
                DispatchTask(
                    task_id="task-002",
                    order_id=1,
                    status="created",
                    idempotency_key="key-002",
                )
            )
            session.add(
                Dispatch(
                    dispatch_no="DSP-duplicate",
                    order_id=1,
                    task_id=first_task.id,
                    status="REROUTED",
                )
            )
            session.commit()
        monkeypatch.setattr(
            dispatch_service_module,
            "uuid4",
            lambda: SimpleNamespace(hex="duplicate"),
        )

        with pytest.raises(IntegrityError):
            DispatchService(factory).execute(
                "task-002",
                1,
                "xinping-road",
                "national-102",
                "REROUTE",
                "safer",
                False,
                None,
                False,
            )

        with factory() as session:
            assert len(list(session.scalars(select(Dispatch)))) == 1
    finally:
        engine.dispose()
        temp.cleanup()


def test_persisted_evidence_replays_audit_and_rejects_tampering() -> None:
    import json
    from copy import deepcopy

    temp, engine, factory = _service()
    try:
        _seed_breakdown_vehicle(factory)
        args = _breakdown_execution_args()
        selected_candidate = args["candidate_vehicles"][0]
        selected_candidate.update(
            {
                "driver_status": "ON_DUTY",
                "remaining_capacity_kg": "900.00",
                "score_components": {
                    "eta_penalty": "9.0",
                    "distance_penalty": "5.60",
                },
                "authorization": "must-not-persist",
            }
        )
        args["candidate_vehicles"].append(
            {
                "vehicle_id": "V-099",
                "driver_id": "D-099",
                "vehicle_status": "MAINTENANCE",
                "driver_status": "OFF_DUTY",
                "remaining_capacity_kg": "100.00",
                "cargo_capability": "GENERAL",
                "score": None,
                "score_components": None,
                "eligible": False,
                "exclusion_reasons": ["VEHICLE_UNAVAILABLE"],
                "authorization": "must-not-persist",
            }
        )
        args["fleet_evidence"] = {
            "algorithm_version": "FLEET_SCORE_V1",
            "candidates": args["candidate_vehicles"],
        }
        route_evidence = {
            "algorithm_version": "DIJKSTRA_V1",
            "road_network_version": 7,
            "original_path": {
                "node_ids": ["N01", "N04"],
                "edge_ids": ["E-ORIGINAL"],
            },
            "recommended_path": {
                "node_ids": ["N04", "N06"],
                "edge_ids": ["E-RECOMMENDED"],
            },
            "pickup_route": {
                "node_ids": ["N15", "N04"],
                "edge_ids": ["E-PICKUP"],
            },
            "blocked_edge_ids": ["E-BLOCKED"],
            "road_network_edges": [
                {
                    "edge_id": "E-ORIGINAL",
                    "from_node_id": "N01",
                    "to_node_id": "N04",
                    "status": "OPEN",
                    "bidirectional": True,
                },
                {
                    "edge_id": "E-RECOMMENDED",
                    "from_node_id": "N04",
                    "to_node_id": "N06",
                    "status": "OPEN",
                    "bidirectional": True,
                },
                {
                    "edge_id": "E-PICKUP",
                    "from_node_id": "N15",
                    "to_node_id": "N04",
                    "status": "OPEN",
                    "bidirectional": True,
                },
                {
                    "edge_id": "E-BLOCKED",
                    "from_node_id": "N02",
                    "to_node_id": "N03",
                    "status": "BLOCKED",
                    "bidirectional": True,
                },
                {
                    "edge_id": "E-UNRELATED",
                    "from_node_id": "N20",
                    "to_node_id": "N21",
                    "status": "OPEN",
                    "bidirectional": True,
                    "authorization": "must-not-persist",
                },
            ],
        }
        args["route_evidence"] = route_evidence

        dispatch = DispatchService(factory).execute(**args)
        initial_evidence = {
            "task_id": "task-001",
            "decision": "REROUTE",
            "recommended_route": "RTE-RECOMMENDED",
            "identified_issue": "VEHICLE_BREAKDOWN",
            "fallback_used": False,
            "memory_adopted": False,
            "vehicle_id": "V-001",
            "selected_vehicle_id": "V-005",
            "selected_driver_id": "D-003",
            "candidate_vehicles": args["candidate_vehicles"],
            "cargo_weight_kg": "700.00",
            "cargo_type": "COLD_CHAIN",
            "blocked_edge_ids": ["E-BLOCKED"],
            "recommended_path": route_evidence["recommended_path"],
            "road_network_edges": route_evidence["road_network_edges"],
            "dispatch_result": {
                "dispatch_id": dispatch.dispatch_id,
                "target_route_id": dispatch.target_route_id,
                "executed": dispatch.executed,
                "original_vehicle_id": dispatch.original_vehicle_id,
                "target_vehicle_id": dispatch.target_vehicle_id,
                "target_driver_id": dispatch.target_driver_id,
            },
        }
        initial_audit = AuditService(factory).audit(initial_evidence)
        assert initial_audit.audit_status == "APPROVED"

        with factory() as session:
            stored_evidence = {
                row.evidence_type: row.payload_json
                for row in session.scalars(select(DispatchEvidence).where(DispatchEvidence.dispatch_id == dispatch.dispatch_id))
            }
            audit_record = session.get(AuditRecord, initial_audit.audit_record_id)
            assert audit_record is not None
            audit_payload = json.loads(audit_record.evidence_json)

        fleet_payload = stored_evidence["FLEET_ALLOCATION"]
        route_payload = stored_evidence["ROUTE_CALCULATION"]
        assert fleet_payload["selected_candidate"] == {
            "vehicle_id": "V-005",
            "driver_id": "D-003",
            "vehicle_status": "AVAILABLE",
            "driver_status": "ON_DUTY",
            "remaining_capacity_kg": "900.00",
            "cargo_capability": "COLD_CHAIN",
            "score": "93.4",
            "score_components": {
                "eta_penalty": "9.0",
                "distance_penalty": "5.60",
            },
            "eligible": True,
            "exclusion_reasons": [],
        }
        assert fleet_payload["candidates"][1] == {
            "vehicle_id": "V-099",
            "score": None,
            "exclusion_reasons": ["VEHICLE_UNAVAILABLE"],
        }
        assert route_payload["original_path"]["edge_ids"] == ["E-ORIGINAL"]
        assert route_payload["recommended_path"]["edge_ids"] == ["E-RECOMMENDED"]
        assert route_payload["pickup_path"]["edge_ids"] == ["E-PICKUP"]
        assert {edge["edge_id"] for edge in route_payload["relevant_edges"]} == {
            "E-ORIGINAL",
            "E-RECOMMENDED",
            "E-PICKUP",
            "E-BLOCKED",
        }
        assert audit_payload["cargo_weight_kg"] == "700.00"
        assert audit_payload["cargo_type"] == "COLD_CHAIN"
        assert audit_payload["dispatch_result"] == initial_evidence["dispatch_result"]
        assert audit_payload["selected_candidate"] == fleet_payload["selected_candidate"]
        assert "authorization" not in json.dumps({"fleet": fleet_payload, "route": route_payload, "audit": audit_payload})

        replay = {
            **audit_payload,
            "candidate_vehicles": [fleet_payload["selected_candidate"]],
            "selected_vehicle_id": fleet_payload["target_vehicle_id"],
            "selected_driver_id": fleet_payload["target_driver_id"],
            "recommended_path": route_payload["recommended_path"],
            "blocked_edge_ids": route_payload["blocked_edge_ids"],
            "road_network_edges": route_payload["relevant_edges"],
        }
        replayed = AuditService(factory).audit(replay)
        assert replayed.audit_status == initial_audit.audit_status == "APPROVED"

        tampered_inputs = []
        tampered_vehicle = deepcopy(replay)
        tampered_vehicle["candidate_vehicles"][0]["vehicle_status"] = "RESERVED"
        tampered_inputs.append(tampered_vehicle)
        tampered_driver = deepcopy(replay)
        tampered_driver["candidate_vehicles"][0]["driver_id"] = "D-999"
        tampered_inputs.append(tampered_driver)
        tampered_capability = deepcopy(replay)
        tampered_capability["candidate_vehicles"][0]["cargo_capability"] = "GENERAL"
        tampered_inputs.append(tampered_capability)
        tampered_edge = deepcopy(replay)
        recommended_edge = next(edge for edge in tampered_edge["road_network_edges"] if edge["edge_id"] == "E-RECOMMENDED")
        recommended_edge["status"] = "BLOCKED"
        tampered_inputs.append(tampered_edge)

        assert all(AuditService(factory).audit(tampered).audit_status == "REJECTED" for tampered in tampered_inputs)
    finally:
        engine.dispose()
        temp.cleanup()
