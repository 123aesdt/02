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


def _row_with_decimals(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    converted = dict(row)
    for field in fields:
        converted[field] = Decimal(converted[field])
    return converted


def _add_if_missing(session: Session, model: type[Any], business_key: str, row: dict[str, Any]) -> None:
    if session.scalar(select(model).where(getattr(model, business_key) == row[business_key])) is None:
        session.add(model(**row))


def seed_new_county_sandtable(session: Session) -> None:
    for row in ROAD_NODES:
        _add_if_missing(session, RoadNode, "node_id", _row_with_decimals(row, "x_km", "y_km"))
    session.flush()

    for row in STATIONS:
        _add_if_missing(
            session,
            LogisticsStation,
            "station_id",
            _row_with_decimals(row, "handling_capacity_kg"),
        )
    for row in DRIVERS:
        driver = dict(row)
        driver["current_vehicle_id"] = None
        _add_if_missing(session, FleetDriver, "driver_id", driver)
    session.flush()

    for row in VEHICLES:
        _add_if_missing(
            session,
            FleetVehicle,
            "vehicle_id",
            _row_with_decimals(row, "max_load_kg", "current_load_kg", "gross_weight_tons"),
        )
    session.flush()

    for row in DRIVERS:
        driver = session.scalar(select(FleetDriver).where(FleetDriver.driver_id == row["driver_id"]))
        if driver is not None and driver.current_vehicle_id is None:
            driver.current_vehicle_id = row["current_vehicle_id"]

    station_names = {row["station_id"]: row["name"] for row in STATIONS}
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
        _add_if_missing(session, RoadEdge, "edge_id", edge)


class SqlAlchemySandtableRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load(self, order_id: int) -> SandtableTaskContext:
        order = self._session.get(Order, order_id)
        if order is None:
            raise LookupError(f"订单不存在: {order_id}")
        origin = self._session.scalar(select(LogisticsStation).where(LogisticsStation.station_id == order.origin_station_id))
        destination = self._session.scalar(select(LogisticsStation).where(LogisticsStation.station_id == order.destination_station_id))
        vehicle = self._session.scalar(select(FleetVehicle).where(FleetVehicle.vehicle_id == order.vehicle_id))
        if origin is None or destination is None or vehicle is None:
            raise LookupError(f"订单沙盘上下文不完整: {order.order_no}")
        road_network_version = self._session.scalar(select(func.max(RoadEdge.version))) or 0
        return SandtableTaskContext(
            order_id=order.id,
            order_no=order.order_no,
            cargo_weight_kg=order.cargo_weight_kg or Decimal("0.00"),
            cargo_type=order.cargo_type or "GENERAL",
            origin_node_id=origin.road_node_id,
            destination_node_id=destination.road_node_id,
            current_vehicle_id=vehicle.vehicle_id,
            current_driver_id=vehicle.assigned_driver_id,
            incident_node_id=None,
            affected_edge_ids=(),
            road_network_version=int(road_network_version),
        )

    def set_edge_status(self, edge_id: str, status: str) -> int:
        edge = self._session.scalar(select(RoadEdge).where(RoadEdge.edge_id == edge_id))
        if edge is None:
            raise LookupError(f"道路不存在: {edge_id}")
        if edge.status == status:
            return edge.version
        edge.status = status
        self._session.commit()
        return edge.version
