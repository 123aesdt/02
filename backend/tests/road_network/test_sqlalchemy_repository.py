from decimal import Decimal

from app.models.road import RoadEdge, RoadNode
from app.road_network.sqlalchemy_repository import SqlAlchemyRoadNetworkRepository


def _node(node_id: str) -> RoadNode:
    return RoadNode(node_id=node_id, name=node_id, x_km=Decimal("1.234"), y_km=Decimal("2.345"), node_type="JUNCTION")


def _edge(edge_id: str, from_node_id: str, to_node_id: str, *, version: int) -> RoadEdge:
    return RoadEdge(
        edge_id=edge_id, name=edge_id, from_node_id=from_node_id, to_node_id=to_node_id, distance_km=Decimal("1.239"), base_minutes=2,
        road_level="COUNTY", risk_level="LOW", status="OPEN", congestion_factor=Decimal("1.25"), weight_limit_tons=Decimal("5.000"), bidirectional=True,
        version=version,
    )


def test_snapshot_returns_immutable_business_id_sorted_dtos_and_latest_edge_version(sqlite_factory) -> None:
    with sqlite_factory() as session:
        session.add_all([_node("N02"), _node("N01")])
        session.flush()
        session.add_all([_edge("E20", "N02", "N01", version=1), _edge("E10", "N01", "N02", version=1)])
        session.commit()
        session.get(RoadEdge, 1).name = "E20-updated"
        session.commit()
        session.get(RoadEdge, 2).name = "E10-updated-once"
        session.commit()
        session.get(RoadEdge, 2).name = "E10-updated-twice"
        session.commit()
        snapshot = SqlAlchemyRoadNetworkRepository(session).snapshot()
    assert snapshot.version == 3
    assert tuple(node.node_id for node in snapshot.nodes) == ("N01", "N02")
    assert tuple(edge.edge_id for edge in snapshot.edges) == ("E10", "E20")
    assert (snapshot.nodes[0].x_km, snapshot.nodes[0].y_km, snapshot.edges[0].distance_km, snapshot.edges[0].weight_limit_tons) == (
        Decimal("1.23"), Decimal("2.35"), Decimal("1.24"), Decimal("5.00")
    )


def test_snapshot_handles_empty_graph_with_version_zero(sqlite_factory) -> None:
    with sqlite_factory() as session:
        snapshot = SqlAlchemyRoadNetworkRepository(session).snapshot()
    assert (snapshot.version, snapshot.nodes, snapshot.edges) == (0, (), ())
