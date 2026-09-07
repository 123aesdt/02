from decimal import Decimal

import pytest

from app.capacity.models import CapacitySnapshot
from app.capacity.provider import InMemoryCapacityProvider
from app.capacity.service import CapacityService
from app.fleet.models import FleetDriverSnapshot, FleetVehicleSnapshot
from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot
from app.road_network.service import RoadNetworkSnapshotService
from app.sandtable.models import SandtableTaskContext
from app.sandtable.seed_data import DRIVERS, ROAD_EDGES, ROAD_NODES, VEHICLES
from app.sandtable.service import SandtableContextService


class _SandtableProvider:
    def __init__(self) -> None:
        self._blocked_edge_ids: set[str] = set()

    def load(self, order_id: int) -> SandtableTaskContext:
        contexts = {
            1: SandtableTaskContext(1, "DEMO-ORDER-001", Decimal("700.00"), "COLD_CHAIN", "N01", "N06", "V-001", "D-001", None, (), 7, Decimal("2.80")),
            5: SandtableTaskContext(5, "DEMO-ORDER-005", Decimal("850.00"), "GENERAL", "N01", "N06", "V-008", "D-007", None, (), 7, Decimal("4.50")),
        }
        return contexts[order_id]

    def set_edge_status(self, edge_id: str, status: str) -> int:
        assert status == "BLOCKED"
        self._blocked_edge_ids.add(edge_id)
        return 8


class _RoadProvider:
    def __init__(self, sandtable: _SandtableProvider) -> None:
        self._sandtable = sandtable

    def snapshot(self) -> RoadNetworkSnapshot:
        return RoadNetworkSnapshot(
            version=8 if self._sandtable._blocked_edge_ids else 7,
            nodes=tuple(RoadNodeSnapshot(row["node_id"], row["name"], Decimal(row["x_km"]), Decimal(row["y_km"]), row["node_type"]) for row in ROAD_NODES),
            edges=tuple(
                RoadEdgeSnapshot(
                    row["edge_id"],
                    row["name"],
                    row["from_node_id"],
                    row["to_node_id"],
                    Decimal(row["distance_km"]),
                    row["base_minutes"],
                    row["road_level"],
                    row["risk_level"],
                    "BLOCKED" if row["edge_id"] in self._sandtable._blocked_edge_ids else "OPEN",
                    Decimal("1.00"),
                    Decimal(row["weight_limit_tons"]),
                    True,
                    8 if row["edge_id"] in self._sandtable._blocked_edge_ids else 7,
                )
                for row in ROAD_EDGES
            ),
        )


class _FleetProvider:
    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]:
        drivers = {
            row["driver_id"]: FleetDriverSnapshot(row["driver_id"], row["name"], row["license_class"], row["status"], row["current_node_id"]) for row in DRIVERS
        }
        return tuple(
            FleetVehicleSnapshot(
                row["vehicle_id"],
                row["plate_no"],
                row["vehicle_type"],
                Decimal(row["max_load_kg"]),
                Decimal(row["current_load_kg"]),
                row["cargo_capability"],
                Decimal(row["gross_weight_tons"]),
                row["status"],
                row["current_node_id"],
                drivers.get(row["assigned_driver_id"]),
            )
            for row in VEHICLES
        )


@pytest.fixture
def graph():
    sandtable_provider = _SandtableProvider()
    sandtable_service = SandtableContextService(sandtable_provider)
    road_provider = _RoadProvider(sandtable_provider)
    path_finder = DijkstraPathFinder()
    return build_graph(
        GraphDependencies(
            sandtable_context_service=sandtable_service,
            fleet_allocation_service=FleetAllocationService(_FleetProvider(), DijkstraTravelTimeEstimator(road_provider, path_finder)),
            road_network_snapshot_service=RoadNetworkSnapshotService(road_provider),
            routing_service=__import__("app.routing.service", fromlist=["RoutingService"]).RoutingService(
                None, memory_adoption_threshold=0.75, road_network_provider=road_provider, path_finder=path_finder
            ),
            capacity_service=CapacityService(
                InMemoryCapacityProvider(
                    {
                        ("D-001", "V-001"): CapacitySnapshot(True, True, 0.45, 0.60, "test"),
                        ("D-007", "V-008"): CapacitySnapshot(True, True, 0.45, 0.60, "test"),
                    }
                ),
                limited_threshold=0.8,
                unavailable_threshold=1.0,
            ),
        )
    )


@pytest.fixture
def breakdown_state() -> dict[str, object]:
    return {
        "task_id": "offline-breakdown-001",
        "order_id": 1,
        "driver_id": "D-001",
        "vehicle_id": "V-001",
        "vehicle_status": "BROKEN",
        "route_id": "xinping-road",
        "anomaly_type": "VEHICLE_BREAKDOWN",
        "anomaly_description": "新物冷链-01 在新平路 K3.2 发动机故障，无法继续配送。",
    }


@pytest.fixture
def blocked_state() -> dict[str, object]:
    return {
        "task_id": "offline-blocked-005",
        "order_id": 5,
        "driver_id": "D-007",
        "vehicle_id": "V-008",
        "route_id": "xinping-road",
        "anomaly_type": "ROAD_BLOCKED",
        "anomaly_description": "新平路东河桥段发生塌方，车辆无法通行。",
    }


@pytest.mark.asyncio
async def test_vehicle_breakdown_reassigns_vehicle_and_continues_to_routing(graph, breakdown_state) -> None:
    result = await graph.ainvoke(breakdown_state)

    assert result["capacity_state"]["capacity_status"] == "REASSIGNED"
    assert result["selected_vehicle_id"] == "V-005"
    assert result["selected_driver_id"] == "D-003"
    assert result["selected_vehicle_gross_weight_tons"] == "2.40"
    assert result["original_vehicle_weight_tons"] == "2.80"
    assert result["active_vehicle_weight_tons"] == "2.40"
    assert result["vehicle_reassigned"] is True
    assert result["pickup_route"]["edge_ids"] == ["E20"]
    assert result["recommended_path"]["node_ids"][-1] == "N06"
    assert result["requires_manual_review"] is False


@pytest.mark.asyncio
async def test_road_block_replans_without_e04(graph, blocked_state) -> None:
    result = await graph.ainvoke(blocked_state)

    assert result["blocked_edge_ids"] == ["E04"]
    assert result["original_path"]["edge_ids"] == ["E01", "E02", "E03", "E04", "E05"]
    assert result["recommended_path"]["edge_ids"] == ["E01", "E06", "E07", "E08", "E09"]
    assert result["distance_delta_km"] == "3.20"
    assert result["eta_delta_minutes"] == 4
    assert result["routing_algorithm"] == "DIJKSTRA_V1"
    assert result["original_vehicle_weight_tons"] == result["active_vehicle_weight_tons"] == "4.50"


@pytest.mark.asyncio
async def test_fixed_scenarios_include_fleet_and_route_scoring_evidence(graph, breakdown_state, blocked_state) -> None:
    breakdown = await graph.ainvoke(breakdown_state)
    selected = next(candidate for candidate in breakdown["candidate_vehicles"] if candidate["vehicle_id"] == "V-005")

    assert selected["score"] in {"93.4", "93.40"}
    assert selected["scoring_formula"] == "FLEET_SCORE_V1"
    assert selected["cargo_capability"] == "COLD_CHAIN"
    assert selected["score_components"] == {
        "eta_penalty": "9.0",
        "distance_penalty": "5.60",
        "load_penalty": "2.0",
        "road_risk_penalty": "0",
        "same_station_bonus": "0",
        "cargo_exact_match_bonus": "10",
    }

    blocked = await graph.ainvoke(blocked_state)

    assert blocked["routing_algorithm"] == "DIJKSTRA_V1"
    assert blocked["recommended_path"]["scoring_formula"] == "ROUTE_SCORE_V1"
    assert all(candidate["scoring_formula"] == "ROUTE_SCORE_V1" for candidate in blocked["candidate_routes"])
    assert all(candidate["algorithm_version"] == "DIJKSTRA_V1" for candidate in blocked["candidate_routes"])
    for candidate in blocked["candidate_routes"]:
        components = candidate["score_components"]
        assert set(components) == {
            "normalized_minutes",
            "normalized_distance",
            "normalized_risk",
            "time_penalty",
            "distance_penalty",
            "risk_penalty",
        }
        assert all(isinstance(value, str) for value in components.values())
        assert Decimal(candidate["score"]) == (
            Decimal("100") - Decimal(components["time_penalty"]) - Decimal(components["distance_penalty"]) - Decimal(components["risk_penalty"])
        )


class _NoReachableRoadProvider:
    def snapshot(self) -> RoadNetworkSnapshot:
        return RoadNetworkSnapshot(
            version=99,
            nodes=tuple(RoadNodeSnapshot(row["node_id"], row["name"], Decimal(row["x_km"]), Decimal(row["y_km"]), row["node_type"]) for row in ROAD_NODES),
            edges=tuple(
                RoadEdgeSnapshot(
                    row["edge_id"],
                    row["name"],
                    row["from_node_id"],
                    row["to_node_id"],
                    Decimal(row["distance_km"]),
                    row["base_minutes"],
                    row["road_level"],
                    row["risk_level"],
                    "BLOCKED",
                    Decimal("1.00"),
                    Decimal(row["weight_limit_tons"]),
                    True,
                    99,
                )
                for row in ROAD_EDGES
            ),
        )


@pytest.fixture
def unreachable_graph():
    sandtable_provider = _SandtableProvider()
    road_provider = _NoReachableRoadProvider()
    return build_graph(
        GraphDependencies(
            sandtable_context_service=SandtableContextService(sandtable_provider),
            road_network_snapshot_service=RoadNetworkSnapshotService(road_provider),
            routing_service=__import__("app.routing.service", fromlist=["RoutingService"]).RoutingService(
                None,
                memory_adoption_threshold=0.75,
                road_network_provider=road_provider,
                path_finder=DijkstraPathFinder(),
            ),
        )
    )


@pytest.mark.asyncio
async def test_unreachable_graph_returns_stable_route_error(unreachable_graph, blocked_state) -> None:
    result = await unreachable_graph.ainvoke(blocked_state)

    assert result["routing_status"] == "NO_REACHABLE_ROUTE"
    assert result["error_code"] == "NO_REACHABLE_ROUTE"
    assert result["error_message"] == "排除受影响道路后不存在可达配送路线，请人工复核。"
    assert result["requires_manual_review"] is True
