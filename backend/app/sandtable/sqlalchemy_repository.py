from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fleet_driver import FleetDriver
from app.models.fleet_vehicle import FleetVehicle
from app.models.order import Order
from app.models.road import RoadEdge, RoadNode
from app.models.station import LogisticsStation
from app.sandtable.models import SandtableTaskContext
from app.sandtable.seed_data import DRIVERS, ORDERS, ROAD_EDGES, ROAD_NODES, STATIONS, VEHICLES

_LIVE_MAP_EDGE_MINUTE_UPGRADES = {
    "E27": (9, 15),
    "E32": (3, 7),
    "E33": (5, 9),
    "E34": (4, 7),
}
_STANDBY_DRIVER_ASSIGNMENTS = {
    "V-003": "D-011",
    "V-011": "D-012",
}
_STANDBY_DRIVER_IDS = frozenset(_STANDBY_DRIVER_ASSIGNMENTS.values())



def _row_with_decimals(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    converted = dict(row)
    for field in fields:
        converted[field] = Decimal(converted[field])
    return converted


def _add_if_missing(session: Session, model: type[Any], business_key: str, row: dict[str, Any]) -> bool:
    if session.scalar(select(model).where(getattr(model, business_key) == row[business_key])) is None:
        session.add(model(**row))
        return True
    return False


class SandtableOrderConflictError(ValueError):
    pass


def _matches_sandtable_order(order: Order, row: dict[str, Any], station_names: dict[str, str]) -> bool:
    return (
        order.status,
        order.driver_id,
        order.vehicle_id,
        order.route_id,
        order.origin,
        order.destination,
        str(order.cargo_weight_kg),
        order.cargo_type,
        order.origin_station_id,
        order.destination_station_id,
    ) == (
        row["status"],
        None,
        row["vehicle_id"],
        None,
        station_names[row["origin_station_id"]],
        station_names[row["destination_station_id"]],
        row["cargo_weight_kg"],
        row["cargo_type"],
        row["origin_station_id"],
        row["destination_station_id"],
    )


def seed_new_county_sandtable(session: Session) -> None:
    station_names = {row["station_id"]: row["name"] for row in STATIONS}
    for row in ORDERS:
        existing = session.scalar(select(Order).where(Order.order_no == row["order_no"]))
        if existing is not None and not _matches_sandtable_order(existing, row, station_names):
            raise SandtableOrderConflictError(f"沙盘订单键冲突且指纹不匹配: {row['order_no']}")

    with session.begin_nested():
        for row in ROAD_NODES:
            _add_if_missing(session, RoadNode, "node_id", _row_with_decimals(row, "x_km", "y_km"))
        session.flush()
        for row in STATIONS:
            _add_if_missing(session, LogisticsStation, "station_id", _row_with_decimals(row, "handling_capacity_kg"))
        new_driver_ids: set[str] = set()
        for row in DRIVERS:
            driver = dict(row)
            driver["current_vehicle_id"] = None
            if _add_if_missing(session, FleetDriver, "driver_id", driver):
                new_driver_ids.add(row["driver_id"])
        session.flush()
        for row in VEHICLES:
            vehicle_row = _row_with_decimals(row, "max_load_kg", "current_load_kg", "gross_weight_tons")
            if row["vehicle_id"] in _STANDBY_DRIVER_ASSIGNMENTS:
                vehicle_row["assigned_driver_id"] = None
            _add_if_missing(session, FleetVehicle, "vehicle_id", vehicle_row)
        session.flush()
        for vehicle_id, driver_id in _STANDBY_DRIVER_ASSIGNMENTS.items():
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == vehicle_id))
            driver = session.scalar(select(FleetDriver).where(FleetDriver.driver_id == driver_id))
            if (
                vehicle is not None
                and driver is not None
                and vehicle.status == "AVAILABLE"
                and driver.status == "ON_DUTY"
                and vehicle.assigned_driver_id in (None, driver.driver_id)
                and driver.current_vehicle_id in (None, vehicle.vehicle_id)
            ):
                vehicle.assigned_driver_id = driver.driver_id
                driver.current_vehicle_id = vehicle.vehicle_id
        for row in DRIVERS:
            if row["driver_id"] in new_driver_ids and row["driver_id"] not in _STANDBY_DRIVER_IDS:
                driver = session.scalar(select(FleetDriver).where(FleetDriver.driver_id == row["driver_id"]))
                if driver is not None:
                    driver.current_vehicle_id = row["current_vehicle_id"]
        for row in ORDERS:
            order = _row_with_decimals(row, "cargo_weight_kg")
            order["origin"] = station_names[order["origin_station_id"]]
            order["destination"] = station_names[order["destination_station_id"]]
            order["driver_id"] = None
            order["route_id"] = None
            _add_if_missing(session, Order, "order_no", order)
        for row in ROAD_EDGES:
            edge = _row_with_decimals(row, "distance_km", "weight_limit_tons")
            edge["status"] = "OPEN"
            edge["congestion_factor"] = Decimal("1.00")
            edge["bidirectional"] = True
            existing_edge = session.scalar(select(RoadEdge).where(RoadEdge.edge_id == edge["edge_id"]))
            if existing_edge is None:
                session.add(RoadEdge(**edge))
                continue
            upgrade = _LIVE_MAP_EDGE_MINUTE_UPGRADES.get(existing_edge.edge_id)
            if (
                upgrade is not None
                and existing_edge.from_node_id == edge["from_node_id"]
                and existing_edge.to_node_id == edge["to_node_id"]
                and existing_edge.base_minutes == upgrade[0]
            ):
                existing_edge.base_minutes = upgrade[1]


class SqlAlchemySandtableRepository:
    def __init__(self, session: Session | object) -> None:
        self._session = session

    def load(self, order_id: int) -> SandtableTaskContext:
        owns = callable(self._session)
        session = self._session() if owns else self._session
        try:
            order = session.get(Order, order_id)
            if order is None:
                raise LookupError(f"订单不存在: {order_id}")
            origin_node_id = self._endpoint_node_id(
                session,
                station_id=order.origin_station_id,
                endpoint_name=order.origin,
            )
            destination_node_id = self._endpoint_node_id(
                session,
                station_id=order.destination_station_id,
                endpoint_name=order.destination,
            )
            vehicle = session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == order.vehicle_id))
            if origin_node_id is None or destination_node_id is None or vehicle is None:
                raise LookupError(f"订单沙盘上下文不完整: {order.order_no}")
            version = session.scalar(select(func.max(RoadEdge.version))) or 0
            return SandtableTaskContext(
                order.id,
                order.order_no,
                order.cargo_weight_kg or Decimal("0.00"),
                order.cargo_type or "GENERAL",
                origin_node_id,
                destination_node_id,
                vehicle.vehicle_id,
                vehicle.assigned_driver_id,
                None,
                (),
                int(version),
                vehicle.gross_weight_tons,
            )
        finally:
            if owns:
                session.close()

    @staticmethod
    def _endpoint_node_id(
        session: Session,
        *,
        station_id: str | None,
        endpoint_name: str,
    ) -> str | None:
        if station_id is not None:
            station = session.scalar(
                select(LogisticsStation).where(LogisticsStation.station_id == station_id)
            )
            if station is not None:
                return station.road_node_id
        nodes = session.scalars(
            select(RoadNode).where(RoadNode.name == endpoint_name)
        ).all()
        return nodes[0].node_id if len(nodes) == 1 else None

    def set_edge_status(self, edge_id: str, status: str) -> int:
        owns = callable(self._session)
        session = self._session() if owns else self._session
        try:
            edge = session.scalar(select(RoadEdge).where(RoadEdge.edge_id == edge_id))
            if edge is None:
                raise LookupError(f"道路不存在: {edge_id}")
            if edge.status != status:
                edge.status = status
                session.commit()
            return edge.version
        finally:
            if owns:
                session.close()
