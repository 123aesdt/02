"""规划双重量与单任务固定路网快照回归。"""

import json
from decimal import Decimal

import pytest

from app.agents.routing import routing_node
from app.fleet.models import FleetDriverSnapshot, FleetVehicleSnapshot
from app.fleet.service import DijkstraTravelTimeEstimator, FleetAllocationService
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot
from app.road_network.service import RoadNetworkSnapshotService
from app.routing.service import RoutingService
from app.sandtable.models import SandtableTaskContext
from app.sandtable.service import SandtableContextService


def _snapshot(version: int, suffix: str) -> RoadNetworkSnapshot:
    nodes = tuple(
        RoadNodeSnapshot(node_id, node_id, Decimal(x), Decimal(y), node_type)
        for node_id, x, y, node_type in (
            ("N15", "-1", "0", "STATION"),
            ("N04", "0", "0", "INCIDENT"),
            ("N05", "1", "1", "WAYPOINT"),
            ("N06", "2", "0", "CUSTOMER"),
        )
    )

    def edge(
        edge_id: str,
        from_node_id: str,
        to_node_id: str,
        distance_km: str,
        base_minutes: int,
        weight_limit_tons: str,
    ) -> RoadEdgeSnapshot:
        return RoadEdgeSnapshot(
            edge_id,
            edge_id,
            from_node_id,
            to_node_id,
            Decimal(distance_km),
            base_minutes,
            "COUNTY",
            "LOW",
            "OPEN",
            Decimal("1.00"),
            Decimal(weight_limit_tons),
            True,
            version,
        )

    return RoadNetworkSnapshot(
        version,
        nodes,
        (
            edge(f"PICK-{suffix}", "N15", "N04", "1.00", 2, "10.00"),
            edge(f"DIRECT-{suffix}", "N04", "N06", "1.00", 1, "3.00"),
            edge(f"DETOUR-{suffix}-1", "N04", "N05", "2.00", 3, "10.00"),
            edge(f"DETOUR-{suffix}-2", "N05", "N06", "2.00", 3, "10.00"),
        ),
    )


class _StaticRoadProvider:
    def __init__(self, snapshot: RoadNetworkSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> RoadNetworkSnapshot:
        return self._snapshot


@pytest.mark.asyncio
async def test_original_path_uses_original_vehicle_weight_and_recommendation_uses_replacement_weight() -> None:
    service = RoutingService(
        None,
        memory_adoption_threshold=Decimal("0.75"),
        road_network_provider=_StaticRoadProvider(_snapshot(1, "A")),
        path_finder=DijkstraPathFinder(),
    )
    state = {
        "task_id": "dual-weight-001",
        "order_id": 1,
        "driver_id": "D-HEAVY",
        "vehicle_id": "V-HEAVY",
        "vehicle_status": "BROKEN",
        "route_id": "R-001",
        "anomaly_type": "VEHICLE_BREAKDOWN",
        "anomaly_description": "原配送车辆故障，已完成换车。",
        "cargo_weight_kg": "500.00",
        "cargo_type": "GENERAL",
        "origin_node_id": "N04",
        "destination_node_id": "N06",
        "incident_node_id": "N04",
        "affected_edge_ids": [],
        "vehicle_weight_tons": "4.50",
        "original_vehicle_weight_tons": "4.50",
        "selected_vehicle_id": "V-LIGHT",
        "selected_driver_id": "D-LIGHT",
        "selected_vehicle_gross_weight_tons": "2.40",
        "active_vehicle_weight_tons": "2.40",
        "capacity_state": {
            "driver_available": True,
            "vehicle_available": True,
            "load_ratio": 0.0,
            "station_load_ratio": None,
            "capacity_status": "REASSIGNED",
            "risk_level": "low",
            "reason": None,
            "provider_name": "test",
        },
    }

    result = await routing_node(state, service)

    assert result["original_path"]["edge_ids"] == ["DETOUR-A-1", "DETOUR-A-2"]
    assert result["recommended_path"]["edge_ids"] == ["DIRECT-A"]
    assert result["distance_delta_km"] == "-3.00"
    assert result["eta_delta_minutes"] == -5


class _MutableRoadProvider:
    def __init__(self) -> None:
        self.current = _snapshot(1, "A")
        self.calls = 0

    def snapshot(self) -> RoadNetworkSnapshot:
        self.calls += 1
        return self.current

    def advance(self) -> None:
        self.current = _snapshot(2, "B")


class _AdvancingFleetProvider:
    def __init__(self, road_provider: _MutableRoadProvider) -> None:
        self._road_provider = road_provider

    def list_candidates(self, excluding_vehicle_id: str) -> tuple[FleetVehicleSnapshot, ...]:
        self._road_provider.advance()
        return (
            FleetVehicleSnapshot(
                "V-LIGHT",
                "云A-LIGHT",
                "VAN",
                Decimal("1500.00"),
                Decimal("100.00"),
                "GENERAL",
                Decimal("2.40"),
                "AVAILABLE",
                "N15",
                FleetDriverSnapshot("D-LIGHT", "测试司机", "C1", "ON_DUTY", "N15"),
            ),
        )


class _SandtableProvider:
    def load(self, order_id: int) -> SandtableTaskContext:
        return SandtableTaskContext(
            order_id,
            f"ORDER-{order_id}",
            Decimal("500.00"),
            "GENERAL",
            "N04",
            "N06",
            "V-HEAVY",
            "D-HEAVY",
            None,
            (),
            999,
            Decimal("4.50"),
        )

    def set_edge_status(self, edge_id: str, status: str) -> int:
        raise AssertionError("车辆故障场景不应修改道路状态")


def _breakdown_state(task_id: str, order_id: int) -> dict[str, object]:
    return {
        "task_id": task_id,
        "order_id": order_id,
        "driver_id": "D-HEAVY",
        "vehicle_id": "V-HEAVY",
        "vehicle_status": "BROKEN",
        "route_id": "R-001",
        "anomaly_type": "VEHICLE_BREAKDOWN",
        "anomaly_description": "原配送车辆在新平路 K3.2 故障。",
    }


@pytest.mark.asyncio
async def test_graph_invocation_uses_one_json_safe_snapshot_and_next_invocation_refreshes_it() -> None:
    road_provider = _MutableRoadProvider()
    finder = DijkstraPathFinder()
    graph = build_graph(
        GraphDependencies(
            sandtable_context_service=SandtableContextService(_SandtableProvider()),
            road_network_snapshot_service=RoadNetworkSnapshotService(road_provider),
            fleet_allocation_service=FleetAllocationService(
                _AdvancingFleetProvider(road_provider),
                DijkstraTravelTimeEstimator(road_provider, finder),
            ),
            routing_service=RoutingService(
                None,
                memory_adoption_threshold=Decimal("0.75"),
                road_network_provider=road_provider,
                path_finder=finder,
            ),
        )
    )

    first = await graph.ainvoke(_breakdown_state("snapshot-A", 1))

    assert road_provider.calls == 1
    assert first["original_vehicle_weight_tons"] == "4.50"
    assert first["active_vehicle_weight_tons"] == "2.40"
    assert first["road_network_version"] == 1
    assert first["pickup_route"]["edge_ids"] == ["PICK-A"]
    assert first["candidate_vehicles"][0]["pickup_route"]["edge_ids"] == ["PICK-A"]
    assert first["original_path"]["edge_ids"] == ["DETOUR-A-1", "DETOUR-A-2"]
    assert first["recommended_path"]["edge_ids"] == ["DIRECT-A"]
    assert all(edge["edge_id"].endswith("A") or "-A-" in edge["edge_id"] for edge in first["road_network_edges"])
    json.dumps(first["road_network_snapshot"])

    second = await graph.ainvoke(_breakdown_state("snapshot-B", 2))

    assert road_provider.calls == 2
    assert second["road_network_version"] == 2
    assert second["pickup_route"]["edge_ids"] == ["PICK-B"]
    assert second["recommended_path"]["edge_ids"] == ["DIRECT-B"]
    assert all(edge["edge_id"].endswith("B") or "-B-" in edge["edge_id"] for edge in second["road_network_edges"])
