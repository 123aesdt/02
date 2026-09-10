import heapq
from collections import defaultdict
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.road_network.models import PathResult, RoadEdgeSnapshot, RoadNetworkSnapshot, RouteObjective

_DISTANCE_QUANTUM = Decimal("0.01")
_RISK_PENALTIES = {"LOW": Decimal("0"), "MEDIUM": Decimal("4"), "HIGH": Decimal("12")}


def _weight(edge: RoadEdgeSnapshot, objective: RouteObjective) -> Decimal:
    minutes = Decimal(edge.base_minutes) * edge.congestion_factor
    if objective == RouteObjective.SHORTEST:
        return edge.distance_km
    if objective == RouteObjective.FASTEST:
        return minutes
    return minutes + _risk_penalty(edge)


def _risk_penalty(edge: RoadEdgeSnapshot) -> Decimal:
    return _RISK_PENALTIES[edge.risk_level]


def _quantize_distance(distance_km: Decimal) -> Decimal:
    return distance_km.quantize(_DISTANCE_QUANTUM, rounding=ROUND_HALF_UP)


class DijkstraPathFinder:
    def find(
        self,
        snapshot: RoadNetworkSnapshot,
        start_node_id: str,
        end_node_id: str,
        objective: RouteObjective,
        vehicle_weight_tons: Decimal,
        excluded_edge_ids: frozenset[str] = frozenset(),
    ) -> PathResult | None:
        node_ids = {node.node_id for node in snapshot.nodes}
        if start_node_id not in node_ids or end_node_id not in node_ids:
            return None
        if start_node_id == end_node_id:
            return PathResult(objective, (start_node_id,), (), Decimal("0.00"), 0, Decimal("0.00"), 0)

        adjacency: dict[str, list[tuple[str, RoadEdgeSnapshot]]] = defaultdict(list)
        for edge in snapshot.edges:
            if not self._is_available(edge, vehicle_weight_tons, excluded_edge_ids):
                continue
            adjacency[edge.from_node_id].append((edge.to_node_id, edge))
            if edge.bidirectional:
                adjacency[edge.to_node_id].append((edge.from_node_id, edge))
        for neighbours in adjacency.values():
            neighbours.sort(key=lambda item: (item[1].edge_id, item[0]))

        zero = Decimal("0")
        best: dict[str, tuple[Decimal, tuple[str, ...]]] = {start_node_id: (zero, ())}
        heap: list[tuple[Decimal, tuple[str, ...], str, tuple[str, ...], Decimal, Decimal]] = [
            (zero, (), start_node_id, (start_node_id,), zero, zero)
        ]
        visited_node_count = 0

        while heap:
            cost, edge_ids, node_id, node_path, distance_km, risk_cost = heapq.heappop(heap)
            if best.get(node_id) != (cost, edge_ids):
                continue
            visited_node_count += 1
            if node_id == end_node_id:
                minutes = self._display_minutes(snapshot, edge_ids)
                return PathResult(objective, node_path, edge_ids, _quantize_distance(distance_km), minutes, risk_cost, visited_node_count)
            for next_node_id, edge in adjacency.get(node_id, ()):
                next_edge_ids = (*edge_ids, edge.edge_id)
                next_cost = cost + _weight(edge, objective)
                candidate = (next_cost, next_edge_ids)
                if next_node_id in best and candidate >= best[next_node_id]:
                    continue
                best[next_node_id] = candidate
                heapq.heappush(
                    heap,
                    (
                        next_cost,
                        next_edge_ids,
                        next_node_id,
                        (*node_path, next_node_id),
                        distance_km + edge.distance_km,
                        risk_cost + _risk_penalty(edge),
                    ),
                )
        return None

    @staticmethod
    def _is_available(
        edge: RoadEdgeSnapshot, vehicle_weight_tons: Decimal, excluded_edge_ids: frozenset[str]
    ) -> bool:
        return edge.edge_id not in excluded_edge_ids and edge.status != "BLOCKED" and vehicle_weight_tons <= edge.weight_limit_tons

    @staticmethod
    def _display_minutes(snapshot: RoadNetworkSnapshot, edge_ids: tuple[str, ...]) -> int:
        edges = {edge.edge_id: edge for edge in snapshot.edges}
        total = sum((Decimal(edges[edge_id].base_minutes) * edges[edge_id].congestion_factor for edge_id in edge_ids), Decimal("0"))
        return int(total.to_integral_value(rounding=ROUND_CEILING))