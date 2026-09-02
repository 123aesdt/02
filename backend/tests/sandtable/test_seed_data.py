from types import MappingProxyType

from app.sandtable.seed_data import DRIVERS, ORDERS, ROAD_EDGES, ROAD_NODES, STATIONS, VEHICLES


def test_new_county_seed_has_the_approved_inventory() -> None:
    assert (len(STATIONS), len(ROAD_NODES), len(ROAD_EDGES)) == (8, 18, 26)
    assert (len(DRIVERS), len(VEHICLES), len(ORDERS)) == (10, 12, 12)
    assert all(isinstance(row, MappingProxyType) for rows in (STATIONS, ROAD_NODES, ROAD_EDGES, DRIVERS, VEHICLES, ORDERS) for row in rows)
    edge = next(item for item in ROAD_EDGES if item["edge_id"] == "E04")
    vehicle = next(item for item in VEHICLES if item["vehicle_id"] == "V-005")
    assert (edge["from_node_id"], edge["to_node_id"], edge["distance_km"], edge["base_minutes"]) == ("N04", "N05", "2.50", 5)
    assert (vehicle["cargo_capability"], vehicle["max_load_kg"], vehicle["current_load_kg"]) == ("COLD_CHAIN", "1000.00", "100.00")
