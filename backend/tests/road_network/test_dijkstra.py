from decimal import Decimal

import pytest

from app.road_network.dijkstra import DijkstraPathFinder
from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot, RouteObjective
from app.sandtable.seed_data import ROAD_EDGES, ROAD_NODES


def _snapshot(*, edges: tuple[RoadEdgeSnapshot, ...] | None = None) -> RoadNetworkSnapshot:
    nodes = tuple(
        RoadNodeSnapshot(
            node_id=row["node_id"], name=row["name"], x_km=Decimal(row["x_km"]), y_km=Decimal(row["y_km"]), node_type=row["node_type"]
        )
        for row in ROAD_NODES
    )
    return RoadNetworkSnapshot(
        version=7,
        nodes=nodes,
        edges=edges
        or tuple(
            RoadEdgeSnapshot(
                edge_id=row["edge_id"],
                name=row["name"],
                from_node_id=row["from_node_id"],
                to_node_id=row["to_node_id"],
                distance_km=Decimal(row["distance_km"]),
                base_minutes=row["base_minutes"],
                road_level=row["road_level"],
                risk_level=row["risk_level"],
                status="OPEN",
                congestion_factor=Decimal("1.00"),
                weight_limit_tons=Decimal(row["weight_limit_tons"]),
                bidirectional=True,
                version=7,
            )
            for row in ROAD_EDGES
        ),
    )


def _edge(
    edge_id: str, from_node_id: str, to_node_id: str, *, distance: str = "1.00", minutes: int = 1, status: str = "OPEN", factor: str = "1.00",
    weight_limit: str = "10.00", bidirectional: bool = True, risk_level: str = "LOW",
) -> RoadEdgeSnapshot:
    return RoadEdgeSnapshot(
        edge_id=edge_id, name=edge_id, from_node_id=from_node_id, to_node_id=to_node_id, distance_km=Decimal(distance), base_minutes=minutes,
        road_level="COUNTY", risk_level=risk_level, status=status, congestion_factor=Decimal(factor), weight_limit_tons=Decimal(weight_limit),
        bidirectional=bidirectional, version=1,
    )


def _small_snapshot(*edges: RoadEdgeSnapshot) -> RoadNetworkSnapshot:
    node_ids = sorted({node_id for edge in edges for node_id in (edge.from_node_id, edge.to_node_id)})
    return RoadNetworkSnapshot(
        version=1,
        nodes=tuple(RoadNodeSnapshot(node_id=node_id, name=node_id, x_km=Decimal("0"), y_km=Decimal("0"), node_type="JUNCTION") for node_id in node_ids),
        edges=tuple(edges),
    )


def test_dijkstra_uses_original_new_road_when_open() -> None:
    result = DijkstraPathFinder().find(_snapshot(), "N01", "N06", RouteObjective.FASTEST, Decimal("2.00"))
    assert result is not None
    assert result.edge_ids == ("E01", "E02", "E03", "E04", "E05")
    assert (result.distance_km, result.estimated_minutes) == (Decimal("10.00"), 20)


def test_dijkstra_excludes_requested_edge_and_calculates_fixed_detour() -> None:
    result = DijkstraPathFinder().find(_snapshot(), "N01", "N06", RouteObjective.FASTEST, Decimal("2.00"), frozenset({"E04"}))
    assert result is not None
    assert result.edge_ids == ("E01", "E06", "E07", "E08", "E09")
    assert (result.distance_km, result.estimated_minutes) == (Decimal("13.20"), 24)
    assert "E04" not in result.edge_ids


def test_route_03_blocks_e10_and_produces_an_executable_detour() -> None:
    finder = DijkstraPathFinder()
    original = finder.find(_snapshot(), "N01", "N11", RouteObjective.FASTEST, Decimal("2.40"))
    rerouted = finder.find(_snapshot(), "N01", "N11", RouteObjective.FASTEST, Decimal("2.40"), frozenset({"E10"}))

    assert original is not None and rerouted is not None
    assert original.edge_ids == ("E10", "E11")
    assert rerouted.edge_ids == ("E14", "E13", "E12", "E11")
    assert rerouted.distance_km - original.distance_km == Decimal("6.50")
    assert rerouted.estimated_minutes - original.estimated_minutes == 13


def test_dijkstra_uses_congestion_multiplier_for_fastest_and_display_minutes() -> None:
    snapshot = _small_snapshot(_edge("E01", "A", "B", minutes=2, factor="2.50"), _edge("E02", "A", "C", minutes=4), _edge("E03", "C", "B", minutes=4))
    result = DijkstraPathFinder().find(snapshot, "A", "B", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert (result.edge_ids, result.estimated_minutes) == (("E01",), 5)


def test_dijkstra_excludes_blocked_edges_before_route_selection() -> None:
    snapshot = _small_snapshot(_edge("E01", "A", "B", status="BLOCKED"), _edge("E02", "A", "C"), _edge("E03", "C", "B"))
    result = DijkstraPathFinder().find(snapshot, "A", "B", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert result.edge_ids == ("E02", "E03")


def test_dijkstra_excludes_restricted_edges_only_when_vehicle_exceeds_limit() -> None:
    snapshot = _small_snapshot(_edge("E01", "A", "B", status="RESTRICTED", weight_limit="2.00"), _edge("E02", "A", "C"), _edge("E03", "C", "B"))
    light = DijkstraPathFinder().find(snapshot, "A", "B", RouteObjective.FASTEST, Decimal("2.00"))
    heavy = DijkstraPathFinder().find(snapshot, "A", "B", RouteObjective.FASTEST, Decimal("2.01"))
    assert light is not None and light.edge_ids == ("E01",)
    assert heavy is not None and heavy.edge_ids == ("E02", "E03")


def test_dijkstra_returns_none_for_disconnected_or_unknown_nodes() -> None:
    snapshot = _small_snapshot(_edge("E01", "A", "B"), _edge("E02", "C", "D"))
    finder = DijkstraPathFinder()
    assert finder.find(snapshot, "A", "D", RouteObjective.FASTEST, Decimal("1.00")) is None
    assert finder.find(snapshot, "A", "MISSING", RouteObjective.FASTEST, Decimal("1.00")) is None


def test_dijkstra_handles_same_start_and_end_without_traversal() -> None:
    result = DijkstraPathFinder().find(_small_snapshot(_edge("E01", "A", "B")), "A", "A", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert (result.node_ids, result.edge_ids, result.distance_km, result.estimated_minutes, result.risk_cost, result.visited_node_count) == (
        ("A",), (), Decimal("0.00"), 0, Decimal("0.00"), 0
    )


def test_dijkstra_traverses_bidirectional_edges_in_reverse_direction() -> None:
    snapshot = _small_snapshot(_edge("E01", "A", "B", bidirectional=True))
    result = DijkstraPathFinder().find(snapshot, "B", "A", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert (result.node_ids, result.edge_ids) == (("B", "A"), ("E01",))


def test_dijkstra_selects_complete_lexical_edge_path_when_costs_tie() -> None:
    snapshot = _small_snapshot(_edge("E20", "A", "B"), _edge("E10", "A", "C"), _edge("E99", "C", "D"), _edge("E30", "B", "D"))
    result = DijkstraPathFinder().find(snapshot, "A", "D", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert result.edge_ids == ("E10", "E99")


@pytest.mark.parametrize(
    ("objective", "expected_edges", "expected_risk"),
    [
        (RouteObjective.SHORTEST, ("E01",), Decimal("12.00")),
        (RouteObjective.SAFEST, ("E02", "E03"), Decimal("0.00")),
    ],
)
def test_dijkstra_respects_objective_and_quantizes_distance(objective: RouteObjective, expected_edges: tuple[str, ...], expected_risk: Decimal) -> None:
    snapshot = _small_snapshot(
        _edge("E01", "A", "B", distance="0.995", minutes=1, risk_level="HIGH"),
        _edge("E02", "A", "C", distance="0.502", minutes=1),
        _edge("E03", "C", "B", distance="0.502", minutes=1),
    )
    result = DijkstraPathFinder().find(snapshot, "A", "B", objective, Decimal("1.00"))
    assert result is not None
    assert (result.edge_ids, result.distance_km, result.risk_cost) == (expected_edges, Decimal("1.00"), expected_risk)


def test_dijkstra_counts_only_current_best_nodes_popped_from_heap() -> None:
    snapshot = _small_snapshot(
        _edge("E01", "A", "B", minutes=9),
        _edge("E02", "A", "C", minutes=1),
        _edge("E03", "C", "B", minutes=1),
        _edge("E04", "B", "D", minutes=1),
    )
    result = DijkstraPathFinder().find(snapshot, "A", "D", RouteObjective.FASTEST, Decimal("1.00"))
    assert result is not None
    assert (result.edge_ids, result.visited_node_count) == (("E02", "E03", "E04"), 4)
