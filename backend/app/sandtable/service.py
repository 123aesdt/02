from dataclasses import replace
from types import MappingProxyType

from app.sandtable.models import SandtableTaskContext
from app.sandtable.protocols import SandtableContextProvider

VEHICLE_ALIASES = MappingProxyType({"新物冷链-01": "V-001"})
NODE_ALIASES = MappingProxyType({"新平路 K3.2": "N04"})
EDGE_ALIASES = MappingProxyType({"新平路东河桥段": "E04", "中心仓至 308 线": "E10"})


class RoadLocationUnresolved(ValueError):
    pass


class VehicleAssignmentMismatch(ValueError):
    def __init__(self, context: SandtableTaskContext) -> None:
        super().__init__("请求车辆与订单当前分配车辆不一致")
        self.context = context


def _resolve_exact_alias(description: str, aliases: MappingProxyType) -> str | None:
    matches = [value for alias, value in aliases.items() if alias in description]
    if len(matches) == 1:
        return matches[0]
    return None


class SandtableContextService:
    def __init__(self, provider: SandtableContextProvider) -> None:
        self._provider = provider

    def resolve(
        self,
        order_id: int,
        anomaly_type: str,
        description: str,
        vehicle_id: str | None,
    ) -> SandtableTaskContext:
        context = self._provider.load(order_id)
        reported_vehicle_id = vehicle_id or _resolve_exact_alias(description, VEHICLE_ALIASES)
        if reported_vehicle_id is not None and reported_vehicle_id != context.current_vehicle_id:
            raise VehicleAssignmentMismatch(context)
        incident_node_id = _resolve_exact_alias(description, NODE_ALIASES)
        if anomaly_type == "ROAD_BLOCKED":
            edge_id = _resolve_exact_alias(description, EDGE_ALIASES)
            if edge_id is None:
                raise RoadLocationUnresolved("无法唯一定位道路")
            self._provider.set_edge_status(edge_id, "BLOCKED")
            context = self._provider.load(order_id)
            return replace(context, affected_edge_ids=(edge_id,))
        return replace(context, incident_node_id=incident_node_id)
