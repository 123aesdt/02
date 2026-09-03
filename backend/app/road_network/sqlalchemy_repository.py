from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.road import RoadEdge, RoadNode
from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot

_QUANTUM = Decimal("0.01")


def _decimal(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


class SqlAlchemyRoadNetworkRepository:
    def __init__(self, session: Session | object) -> None:
        self._session = session

    def snapshot(self) -> RoadNetworkSnapshot:
        owns = callable(self._session)
        session = self._session() if owns else self._session
        try:
            nodes = tuple(
                RoadNodeSnapshot(node.node_id, node.name, _decimal(node.x_km), _decimal(node.y_km), node.node_type)
                for node in session.scalars(select(RoadNode).order_by(RoadNode.node_id))
            )
            edges = tuple(
                RoadEdgeSnapshot(
                    edge.edge_id,
                    edge.name,
                    edge.from_node_id,
                    edge.to_node_id,
                    _decimal(edge.distance_km),
                    edge.base_minutes,
                    edge.road_level,
                    edge.risk_level,
                    edge.status,
                    _decimal(edge.congestion_factor),
                    _decimal(edge.weight_limit_tons),
                    edge.bidirectional,
                    edge.version,
                )
                for edge in session.scalars(select(RoadEdge).order_by(RoadEdge.edge_id))
            )
            return RoadNetworkSnapshot(max((edge.version for edge in edges), default=0), nodes, edges)
        finally:
            if owns:
                session.close()
