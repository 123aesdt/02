from decimal import Decimal

import pytest

from app.graph.state import CapacityState, MemoryRecallState
from app.routing.models import RouteCandidate
from app.routing.provider import InMemoryRouteProvider
from app.routing.service import RoutingService


def _service() -> RoutingService:
    return RoutingService(InMemoryRouteProvider.default_catalog(), memory_adoption_threshold=0.75)


def _memory(score: float = 0.9, resolution: str = "建议改走102国道") -> list[MemoryRecallState]:
    return [
        {
            "memory_id": "memory-rain-li",
            "similarity_score": score,
            "driver_id": "driver-li",
            "route_id": "xinping-road",
            "anomaly_type": "rain_slippery",
            "historical_resolution": resolution,
            "metadata": {},
        }
    ]


def _capacity(status: str = "AVAILABLE") -> CapacityState:
    return {
        "driver_available": True,
        "vehicle_available": True,
        "load_ratio": 0.45,
        "station_load_ratio": 0.60,
        "capacity_status": status,
        "risk_level": "low",
        "reason": None,
        "provider_name": "in_memory_capacity",
    }


@pytest.mark.asyncio
async def test_route_candidate_model():
    candidate = RouteCandidate("xinping-road", "新平路", Decimal("10.0"), 20, "low", True, None, Decimal("80.0"))

    assert candidate.route_name == "新平路"


@pytest.mark.asyncio
async def test_routing_service_normal_route():
    result = await _service().route("xinping-road", [], "clear", "dry", "low", _capacity())

    assert (result.recommended_route, result.decision, result.routing_status) == ("xinping-road", "KEEP_ROUTE", "ROUTED")


@pytest.mark.asyncio
async def test_routing_service_adopts_memory():
    result = await _service().route("xinping-road", _memory(), "heavy_rain", "slippery", "high", _capacity())

    assert result.recommended_route == "national-102"
    assert result.memory_adopted is True
    assert result.adopted_memory_id == "memory-rain-li"
    assert "memory-rain-li" in result.decision_reason


@pytest.mark.asyncio
async def test_routing_service_avoids_risky_route():
    result = await _service().route("xinping-road", _memory(0.20), "heavy_rain", "slippery", "high", _capacity())

    assert result.recommended_route == "national-102"
    assert result.memory_adopted is False
    assert result.candidate_routes[-1].route_id == "xinping-road"
    assert result.candidate_routes[-1].available is False


@pytest.mark.asyncio
async def test_routing_service_capacity_unavailable():
    result = await _service().route("xinping-road", _memory(), "clear", "dry", "low", _capacity("UNAVAILABLE"))

    assert (result.decision, result.requires_manual_review, result.recommended_route) == ("MANUAL_REVIEW", True, None)


@pytest.mark.asyncio
async def test_routing_service_does_not_adopt_unavailable_memory_route():
    result = await _service().route("xinping-road", _memory(), "heavy_rain", "slippery", "high", _capacity())
    closed = await _service().route("xinping-road", _memory(), "unknown", "closed", "critical", _capacity())

    assert result.memory_adopted is True
    assert closed.recommended_route != "xinping-road"
    assert closed.candidate_routes[-1].route_id == "xinping-road"


def test_routing_plan_excludes_two_ton_shortcut_for_heavy_vehicle():
    """4.50t 车辆必须避开 2.00t 限重捷径，且 2.00t 可选择该捷径。"""
    from decimal import Decimal

    from app.road_network.dijkstra import DijkstraPathFinder
    from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot
    from app.sandtable.models import SandtableTaskContext

    class StaticRoadNetwork:
        def snapshot(self) -> RoadNetworkSnapshot:
            return RoadNetworkSnapshot(
                version=1,
                nodes=(
                    RoadNodeSnapshot("A", "起点", Decimal("0"), Decimal("0"), "DEPOT"),
                    RoadNodeSnapshot("B", "终点", Decimal("2"), Decimal("0"), "CUSTOMER"),
                    RoadNodeSnapshot("C", "绕行点", Decimal("1"), Decimal("1"), "JUNCTION"),
                ),
                edges=(
                    RoadEdgeSnapshot("FAST", "限重捷径", "A", "B", Decimal("1.00"), 1, "COUNTY", "LOW", "OPEN", Decimal("1.00"), Decimal("2.00"), False, 1),
                    RoadEdgeSnapshot(
                        "SAFE_1", "可承载绕路一", "A", "C", Decimal("2.00"), 3, "COUNTY", "LOW", "OPEN", Decimal("1.00"), Decimal("10.00"), False, 1
                    ),
                    RoadEdgeSnapshot(
                        "SAFE_2", "可承载绕路二", "C", "B", Decimal("2.00"), 3, "COUNTY", "LOW", "OPEN", Decimal("1.00"), Decimal("10.00"), False, 1
                    ),
                ),
            )

    service = RoutingService(
        None,
        memory_adoption_threshold=0.75,
        road_network_provider=StaticRoadNetwork(),
        path_finder=DijkstraPathFinder(),
    )
    common = (1, "ORDER-1", Decimal("100"), "GENERAL", "A", "B", "V-HEAVY", None, None, (), 1)

    light = service.plan(SandtableTaskContext(*common, Decimal("2.00")), _capacity(), [], [])
    heavy = service.plan(SandtableTaskContext(*common, Decimal("4.50")), _capacity(), [], [])

    assert light.original_path is not None
    assert light.original_path.edge_ids == ("FAST",)
    assert heavy.original_path is not None
    assert heavy.recommended_path is not None
    assert heavy.original_path.edge_ids == ("SAFE_1", "SAFE_2")
    assert heavy.recommended_path.edge_ids == ("SAFE_1", "SAFE_2")
    assert all("FAST" not in candidate.edge_ids for candidate in heavy.candidate_routes)


def test_path_candidates_preserve_decimal_precision_until_json_boundary():
    from decimal import Decimal

    from app.agents.routing import route_candidate_to_state
    from app.road_network.models import PathResult, RouteObjective

    paths = [
        PathResult(RouteObjective.FASTEST, ("A", "B"), ("E-FAST",), Decimal("0.10"), 1, Decimal("0.00"), 2),
        PathResult(RouteObjective.SHORTEST, ("A", "C", "B"), ("E-SHORT",), Decimal("0.30"), 3, Decimal("0.00"), 3),
    ]

    candidates = RoutingService._score_paths(paths, road_network_version=7)
    fastest = next(candidate for candidate in candidates if candidate.edge_ids == ("E-FAST",))
    shortest = next(candidate for candidate in candidates if candidate.edge_ids == ("E-SHORT",))

    assert (fastest.distance_km, fastest.score) == (Decimal("0.10"), Decimal("75.00"))
    assert (shortest.distance_km, shortest.score) == (Decimal("0.30"), Decimal("25.00"))
    assert route_candidate_to_state(fastest)["distance_km"] == "0.10"
    assert route_candidate_to_state(fastest)["score"] == "75.00"


def test_route_plan_breaks_equal_decimal_scores_by_edge_sequence():
    from decimal import Decimal

    from app.road_network.models import PathResult, RoadNetworkSnapshot, RoadNodeSnapshot, RouteObjective
    from app.sandtable.models import SandtableTaskContext

    class StaticRoadNetwork:
        def snapshot(self) -> RoadNetworkSnapshot:
            return RoadNetworkSnapshot(
                version=7,
                nodes=(
                    RoadNodeSnapshot("A", "起点", Decimal("0"), Decimal("0"), "DEPOT"),
                    RoadNodeSnapshot("B", "终点", Decimal("1"), Decimal("0"), "CUSTOMER"),
                ),
                edges=(),
            )

    class TiePathFinder:
        def find(
            self,
            snapshot: RoadNetworkSnapshot,
            start_node_id: str,
            end_node_id: str,
            objective: RouteObjective,
            vehicle_weight_tons: Decimal,
            excluded_edge_ids: frozenset[str] = frozenset(),
        ) -> PathResult:
            if objective == RouteObjective.SHORTEST:
                return PathResult(objective, ("A", "B"), ("E-FAST",), Decimal("20.00"), 10, Decimal("0.00"), 2)
            return PathResult(objective, ("A", "B"), ("E-SLOW",), Decimal("20.00"), 10, Decimal("0.00"), 2)

    service = RoutingService(
        None,
        memory_adoption_threshold=0.75,
        road_network_provider=StaticRoadNetwork(),
        path_finder=TiePathFinder(),
    )
    context = SandtableTaskContext(1, "ORDER-DECIMAL", Decimal("100"), "GENERAL", "A", "B", "V-001", None, None, (), 7, Decimal("2.00"))

    result = service.plan(context, _capacity(), [], [])

    assert result.recommended_path is not None
    assert result.recommended_path.edge_ids == ("E-FAST",)
    assert {candidate.score for candidate in result.candidate_routes} == {Decimal("25.00")}
    assert all(isinstance(candidate.distance_km, Decimal) and isinstance(candidate.score, Decimal) for candidate in result.candidate_routes)


def test_single_path_route_score_components_are_zero():
    from app.road_network.models import PathResult, RouteObjective

    candidate = RoutingService._score_paths(
        [PathResult(RouteObjective.FASTEST, ("A", "B"), ("E-ONLY",), Decimal("2.50"), 5, Decimal("4.00"), 2)],
        road_network_version=3,
    )[0]

    components = candidate.score_components
    assert components is not None
    assert (
        components.normalized_minutes,
        components.normalized_distance,
        components.normalized_risk,
        components.time_penalty,
        components.distance_penalty,
        components.risk_penalty,
        candidate.score,
    ) == (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("100"))


def test_route_score_components_are_decimal_and_exactly_rebuild_total_score():
    from app.road_network.models import PathResult, RouteObjective

    paths = [
        PathResult(RouteObjective.FASTEST, ("A", "B"), ("E-FAST",), Decimal("10.00"), 10, Decimal("0.00"), 2),
        PathResult(RouteObjective.SHORTEST, ("A", "C", "B"), ("E-SHORT",), Decimal("5.00"), 20, Decimal("4.00"), 3),
        PathResult(RouteObjective.SAFEST, ("A", "D", "B"), ("E-SAFE",), Decimal("15.00"), 30, Decimal("12.00"), 4),
    ]

    for candidate in RoutingService._score_paths(paths, road_network_version=7):
        components = candidate.score_components
        assert components is not None
        values = (
            components.normalized_minutes,
            components.normalized_distance,
            components.normalized_risk,
            components.time_penalty,
            components.distance_penalty,
            components.risk_penalty,
        )
        assert all(isinstance(value, Decimal) for value in values)
        assert components.time_penalty == components.normalized_minutes * Decimal("45")
        assert components.distance_penalty == components.normalized_distance * Decimal("30")
        assert components.risk_penalty == components.normalized_risk * Decimal("25")
        assert candidate.score == (Decimal("100") - components.time_penalty - components.distance_penalty - components.risk_penalty)


def test_real_routing_projection_allows_reverse_bidirectional_path_in_audit() -> None:
    from app.audit.service import AuditService
    from app.road_network.dijkstra import DijkstraPathFinder
    from app.road_network.models import (
        RoadEdgeSnapshot,
        RoadNetworkSnapshot,
        RoadNodeSnapshot,
    )
    from app.routing.models import RoutePlanningContext

    snapshot = RoadNetworkSnapshot(
        version=7,
        nodes=(
            RoadNodeSnapshot("A", "甲", Decimal("0"), Decimal("0"), "DEPOT"),
            RoadNodeSnapshot("B", "乙", Decimal("1"), Decimal("0"), "CUSTOMER"),
            RoadNodeSnapshot("C", "丙", Decimal("2"), Decimal("0"), "JUNCTION"),
        ),
        edges=(
            RoadEdgeSnapshot(
                "E-REVERSE",
                "双向道路",
                "A",
                "B",
                Decimal("1.00"),
                2,
                "COUNTY",
                "LOW",
                "OPEN",
                Decimal("1.00"),
                Decimal("10.00"),
                True,
                7,
            ),
            RoadEdgeSnapshot(
                "E-BLOCKED",
                "已阻断道路",
                "B",
                "C",
                Decimal("1.00"),
                2,
                "COUNTY",
                "LOW",
                "BLOCKED",
                Decimal("1.00"),
                Decimal("10.00"),
                True,
                7,
            ),
        ),
    )
    context = RoutePlanningContext(
        order_id=1,
        order_no="ORD-REVERSE",
        cargo_weight_kg=Decimal("100.00"),
        cargo_type="GENERAL",
        origin_node_id="B",
        destination_node_id="A",
        current_vehicle_id="V-001",
        current_driver_id="D-001",
        incident_node_id=None,
        affected_edge_ids=("E-BLOCKED",),
        road_network_version=7,
        original_vehicle_weight_tons=Decimal("2.00"),
        active_vehicle_weight_tons=Decimal("2.00"),
    )
    routing = RoutingService(
        None,
        memory_adoption_threshold=0.75,
        path_finder=DijkstraPathFinder(),
    ).plan(
        context,
        _capacity(),
        ["E-BLOCKED"],
        [],
        road_network_snapshot=snapshot,
    )
    assert routing.recommended_path is not None
    projected_reverse = next(edge for edge in routing.road_network_edges if edge["edge_id"] == "E-REVERSE")
    assert projected_reverse["bidirectional"] is True

    result = AuditService(lambda: None).audit(
        {
            "identified_issue": "ROAD_BLOCKED",
            "decision": "REROUTE",
            "recommended_route": routing.recommended_route,
            "blocked_edge_ids": list(routing.blocked_edge_ids),
            "recommended_path": {
                "node_ids": list(routing.recommended_path.node_ids),
                "edge_ids": list(routing.recommended_path.edge_ids),
            },
            "road_network_edges": routing.road_network_edges,
            "fallback_used": False,
            "dispatch_result": {
                "dispatch_id": 1,
                "target_route_id": routing.recommended_route,
                "executed": True,
            },
        }
    )

    assert result.audit_status == "APPROVED"
    assert result.checks["route_connectivity"] is True


def _plan_single_edge_status(
    status: str,
    *,
    weight_limit_tons: Decimal,
    vehicle_weight_tons: Decimal,
):
    from app.road_network.dijkstra import DijkstraPathFinder
    from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot
    from app.routing.models import RoutePlanningContext

    snapshot = RoadNetworkSnapshot(
        version=9,
        nodes=(
            RoadNodeSnapshot("A", "起点", Decimal("0"), Decimal("0"), "DEPOT"),
            RoadNodeSnapshot("B", "终点", Decimal("1"), Decimal("0"), "CUSTOMER"),
            RoadNodeSnapshot("C", "阻断起点", Decimal("2"), Decimal("0"), "JUNCTION"),
            RoadNodeSnapshot("D", "阻断终点", Decimal("3"), Decimal("0"), "JUNCTION"),
        ),
        edges=(
            RoadEdgeSnapshot(
                "E-STATUS",
                "状态道路",
                "A",
                "B",
                Decimal("1.00"),
                2,
                "COUNTY",
                "LOW",
                status,
                Decimal("1.50"),
                weight_limit_tons,
                True,
                9,
            ),
            RoadEdgeSnapshot(
                "E-BLOCKED",
                "已阻断道路",
                "C",
                "D",
                Decimal("1.00"),
                2,
                "COUNTY",
                "LOW",
                "BLOCKED",
                Decimal("1.00"),
                Decimal("10.00"),
                True,
                9,
            ),
        ),
    )
    context = RoutePlanningContext(
        order_id=1,
        order_no="ORD-STATUS",
        cargo_weight_kg=Decimal("100.00"),
        cargo_type="GENERAL",
        origin_node_id="A",
        destination_node_id="B",
        current_vehicle_id="V-001",
        current_driver_id="D-001",
        incident_node_id=None,
        affected_edge_ids=("E-BLOCKED",),
        road_network_version=9,
        original_vehicle_weight_tons=vehicle_weight_tons,
        active_vehicle_weight_tons=vehicle_weight_tons,
    )
    return RoutingService(
        None,
        memory_adoption_threshold=0.75,
        path_finder=DijkstraPathFinder(),
    ).plan(
        context,
        _capacity(),
        ["E-BLOCKED"],
        [],
        road_network_snapshot=snapshot,
    )


@pytest.mark.parametrize("status", ["CONGESTED", "RESTRICTED"])
def test_real_routing_audit_allows_known_non_blocked_edge_status(status: str) -> None:
    from app.audit.service import AuditService

    routing = _plan_single_edge_status(
        status,
        weight_limit_tons=Decimal("2.00"),
        vehicle_weight_tons=Decimal("2.00"),
    )
    assert routing.recommended_path is not None
    assert routing.recommended_path.edge_ids == ("E-STATUS",)

    result = AuditService(lambda: None).audit(
        {
            "identified_issue": "ROAD_BLOCKED",
            "decision": routing.decision,
            "recommended_route": routing.recommended_route,
            "blocked_edge_ids": list(routing.blocked_edge_ids),
            "recommended_path": {
                "node_ids": list(routing.recommended_path.node_ids),
                "edge_ids": list(routing.recommended_path.edge_ids),
            },
            "road_network_edges": routing.road_network_edges,
            "fallback_used": False,
            "dispatch_result": {
                "dispatch_id": 1,
                "target_route_id": routing.recommended_route,
                "executed": True,
            },
        }
    )

    assert result.audit_status == "APPROVED"
    assert result.checks["blocked_edge_exclusion"] is True


def test_real_routing_rejects_restricted_edge_when_vehicle_exceeds_limit() -> None:
    routing = _plan_single_edge_status(
        "RESTRICTED",
        weight_limit_tons=Decimal("1.99"),
        vehicle_weight_tons=Decimal("2.00"),
    )

    assert routing.recommended_path is None
    assert routing.routing_status == "NO_REACHABLE_ROUTE"
    assert routing.requires_manual_review is True
