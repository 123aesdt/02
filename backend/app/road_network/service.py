from decimal import Decimal

from app.graph.state import RoadNetworkSnapshotState
from app.road_network.models import RoadEdgeSnapshot, RoadNetworkSnapshot, RoadNodeSnapshot
from app.road_network.protocols import RoadNetworkProvider


class RoadNetworkSnapshotService:
    """在任务边界捕获一次路网，并在节点边界安全还原领域快照。"""

    def __init__(self, provider: RoadNetworkProvider) -> None:
        self._provider = provider

    def capture(self) -> RoadNetworkSnapshotState:
        return self.to_state(self._provider.snapshot())

    @staticmethod
    def to_state(snapshot: RoadNetworkSnapshot) -> RoadNetworkSnapshotState:
        return {
            "version": snapshot.version,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "name": node.name,
                    "x_km": format(node.x_km, "f"),
                    "y_km": format(node.y_km, "f"),
                    "node_type": node.node_type,
                }
                for node in snapshot.nodes
            ],
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "name": edge.name,
                    "from_node_id": edge.from_node_id,
                    "to_node_id": edge.to_node_id,
                    "distance_km": format(edge.distance_km, "f"),
                    "base_minutes": edge.base_minutes,
                    "road_level": edge.road_level,
                    "risk_level": edge.risk_level,
                    "status": edge.status,
                    "congestion_factor": format(edge.congestion_factor, "f"),
                    "weight_limit_tons": format(edge.weight_limit_tons, "f"),
                    "bidirectional": edge.bidirectional,
                    "version": edge.version,
                }
                for edge in snapshot.edges
            ],
        }

    @staticmethod
    def restore(state: RoadNetworkSnapshotState) -> RoadNetworkSnapshot:
        return RoadNetworkSnapshot(
            version=state["version"],
            nodes=tuple(
                RoadNodeSnapshot(
                    node["node_id"],
                    node["name"],
                    Decimal(node["x_km"]),
                    Decimal(node["y_km"]),
                    node["node_type"],
                )
                for node in state["nodes"]
            ),
            edges=tuple(
                RoadEdgeSnapshot(
                    edge["edge_id"],
                    edge["name"],
                    edge["from_node_id"],
                    edge["to_node_id"],
                    Decimal(edge["distance_km"]),
                    edge["base_minutes"],
                    edge["road_level"],
                    edge["risk_level"],
                    edge["status"],
                    Decimal(edge["congestion_factor"]),
                    Decimal(edge["weight_limit_tons"]),
                    edge["bidirectional"],
                    edge["version"],
                )
                for edge in state["edges"]
            ),
        )
