"""真实 SQLite 仓储参与的离线调度图组合测试。"""

from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import select

from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
from app.fleet.sqlalchemy_repository import SqlAlchemyFleetRepository
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository
from app.routing.service import RoutingService
from app.sandtable.service import SandtableContextService
from app.sandtable.sqlalchemy_repository import SqlAlchemySandtableRepository, seed_new_county_sandtable


@pytest.mark.asyncio
async def test_sqlite_repositories_run_graph_tasks_with_fresh_snapshot_and_real_vehicle_weight(sqlite_factory) -> None:
    with sqlite_factory() as session:
        seed_new_county_sandtable(session)
        session.add(
            RoadEdge(
                edge_id="E-LIMIT-2T",
                name="两吨限重测试捷径",
                from_node_id="N01",
                to_node_id="N06",
                distance_km=Decimal("0.50"),
                base_minutes=1,
                road_level="COUNTY",
                risk_level="LOW",
                status="OPEN",
                congestion_factor=Decimal("1.00"),
                weight_limit_tons=Decimal("2.00"),
                bidirectional=True,
            )
        )
        session.commit()
        order_ids = dict(session.execute(select(Order.order_no, Order.id)).all())

    sessions = []

    def tracked_factory():
        session = sqlite_factory()
        sessions.append(session)
        return session

    sandtable_repository = SqlAlchemySandtableRepository(tracked_factory)
    road_repository = SqlAlchemyRoadNetworkRepository(tracked_factory)
    fleet_repository = SqlAlchemyFleetRepository(tracked_factory)
    path_finder = DijkstraPathFinder()
    graph = build_graph(
        GraphDependencies(
            sandtable_context_service=SandtableContextService(sandtable_repository),
            fleet_allocation_service=FleetAllocationService(
                fleet_repository,
                DijkstraTravelTimeEstimator(road_repository, path_finder),
            ),
            routing_service=RoutingService(
                None,
                memory_adoption_threshold=0.75,
                road_network_provider=road_repository,
                path_finder=path_finder,
            ),
        )
    )

    mismatched_vehicle = await graph.ainvoke(
        {
            "task_id": "sqlite-mismatched-vehicle-005",
            "order_id": order_ids["DEMO-ORDER-005"],
            "driver_id": "D-007",
            "vehicle_id": "V-001",
            "vehicle_status": "NORMAL",
            "route_id": "xinping-road",
            "anomaly_type": "ROUTE_RISK",
            "anomaly_description": "正常配送车辆身份校验。",
        }
    )
    assert (
        mismatched_vehicle.get("vehicle_id"),
        mismatched_vehicle.get("vehicle_weight_tons"),
        mismatched_vehicle.get("requires_manual_review"),
        mismatched_vehicle.get("error_code"),
        mismatched_vehicle.get("recommended_route"),
        mismatched_vehicle.get("recommended_path"),
    ) == ("V-008", "4.50", True, "VEHICLE_ASSIGNMENT_MISMATCH", None, None)

    source_context = sandtable_repository.load(order_ids["DEMO-ORDER-005"])
    normal_vehicle = await graph.ainvoke(
        {
            "task_id": "sqlite-normal-heavy-005",
            "order_id": order_ids["DEMO-ORDER-005"],
            "driver_id": "D-007",
            "vehicle_id": "V-008",
            "vehicle_status": "NORMAL",
            "route_id": "xinping-road",
            "anomaly_type": "ROUTE_RISK",
            "anomaly_description": "正常配送车辆执行限重道路校验。",
        }
    )

    assert source_context.vehicle_weight_tons == Decimal("4.50")
    assert normal_vehicle["vehicle_weight_tons"] == "4.50"
    assert "E-LIMIT-2T" not in normal_vehicle["original_path"]["edge_ids"]
    assert "E-LIMIT-2T" not in normal_vehicle["recommended_path"]["edge_ids"]
    assert all("E-LIMIT-2T" not in candidate["edge_ids"] for candidate in normal_vehicle["candidate_routes"])

    breakdown = await graph.ainvoke(
        {
            "task_id": "sqlite-breakdown-001",
            "order_id": order_ids["DEMO-ORDER-001"],
            "driver_id": "D-001",
            "vehicle_id": "V-001",
            "vehicle_status": "BROKEN",
            "route_id": "xinping-road",
            "anomaly_type": "VEHICLE_BREAKDOWN",
            "anomaly_description": "新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。",
        }
    )
    before = road_repository.snapshot()
    blocked = await graph.ainvoke(
        {
            "task_id": "sqlite-blocked-005",
            "order_id": order_ids["DEMO-ORDER-005"],
            "driver_id": "D-007",
            "vehicle_id": "V-008",
            "vehicle_status": "NORMAL",
            "route_id": "xinping-road",
            "anomaly_type": "ROAD_BLOCKED",
            "anomaly_description": "新平路东河桥段发生塌方，车辆无法通行。",
        }
    )
    after = road_repository.snapshot()

    assert (breakdown["selected_vehicle_id"], breakdown["selected_driver_id"]) == ("V-005", "D-003")
    assert breakdown["pickup_route"]["edge_ids"] == ["E20"]
    assert breakdown["recommended_path"]["node_ids"][0] == "N04"
    assert breakdown["candidate_vehicles"]
    selected = next(item for item in breakdown["candidate_vehicles"] if item["vehicle_id"] == "V-005")
    assert selected["score"] in {"93.4", "93.40"}

    expected_edges = ["E01", "E06", "E07", "E08", "E09"]
    matching_candidate = next(candidate for candidate in blocked["candidate_routes"] if candidate["edge_ids"] == expected_edges)
    assert matching_candidate["route_id"] == f"RTE-{sha256('|'.join(expected_edges).encode()).hexdigest()[:16].upper()}"
    assert matching_candidate["scoring_formula"] == "ROUTE_SCORE_V1"
    assert len({tuple(candidate["edge_ids"]) for candidate in blocked["candidate_routes"]}) == len(blocked["candidate_routes"])
    assert blocked["recommended_path"]["edge_ids"] == expected_edges
    assert blocked["road_network_nodes"] == [
        {"node_id": node.node_id, "name": node.name, "x_km": str(node.x_km), "y_km": str(node.y_km), "node_type": node.node_type} for node in after.nodes
    ]
    assert next(edge for edge in blocked["road_network_edges"] if edge["edge_id"] == "E04")["status"] == "BLOCKED"
    assert next(edge for edge in after.edges if edge.edge_id == "E04").version > next(edge for edge in before.edges if edge.edge_id == "E04").version

    with sqlite_factory() as session:
        for vehicle in session.scalars(select(FleetVehicle).where(FleetVehicle.vehicle_id != "V-001")):
            vehicle.status = "MAINTENANCE"
        session.commit()
    no_replacement = await graph.ainvoke(
        {
            "task_id": "sqlite-no-replacement-001",
            "order_id": order_ids["DEMO-ORDER-001"],
            "driver_id": "D-001",
            "vehicle_id": "V-001",
            "vehicle_status": "BROKEN",
            "route_id": "xinping-road",
            "anomaly_type": "VEHICLE_BREAKDOWN",
            "anomaly_description": "新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。",
        }
    )

    assert no_replacement["error_code"] == "NO_REPLACEMENT_VEHICLE"
    assert no_replacement["requires_manual_review"] is True
    assert sessions and len({id(session) for session in sessions}) == len(sessions)
    assert all(not session.in_transaction() for session in sessions)
