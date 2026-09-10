import hashlib
import json
from types import MappingProxyType

from app.sandtable.seed_data import DRIVERS, ORDERS, ROAD_EDGES, ROAD_NODES, STATIONS, VEHICLES


def test_new_county_seed_has_the_approved_inventory() -> None:
    assert (len(STATIONS), len(ROAD_NODES), len(ROAD_EDGES)) == (8, 18, 26)
    assert (len(DRIVERS), len(VEHICLES), len(ORDERS)) == (10, 20, 12)
    assert all(isinstance(row, MappingProxyType) for rows in (STATIONS, ROAD_NODES, ROAD_EDGES, DRIVERS, VEHICLES, ORDERS) for row in rows)
    edge = next(item for item in ROAD_EDGES if item["edge_id"] == "E04")
    vehicle = next(item for item in VEHICLES if item["vehicle_id"] == "V-005")
    assert (edge["from_node_id"], edge["to_node_id"], edge["distance_km"], edge["base_minutes"]) == ("N04", "N05", "2.50", 5)
    assert (vehicle["cargo_capability"], vehicle["max_load_kg"], vehicle["current_load_kg"]) == ("COLD_CHAIN", "1000.00", "100.00")


def test_all_approved_rows_match_the_business_id_sorted_contract() -> None:
    collections = (STATIONS, ROAD_NODES, ROAD_EDGES, DRIVERS, VEHICLES, ORDERS)
    expected_digests = (
        "56f7d0313c2ddf02fd469dcc536d77e5617f8f73613b36e7702ea5a92673ea38",
        "5e4effa3e21e7e3ca0c2b33aca8d2fad8ea48900840a0e095f7a8c545d9244d8",
        "77a70b955cb5adeab07e579afe62f8338a17816ad2a28c09b88b1ad99edc80e7",
        "16d6a233b76612c7bbdb0bf9e7db9b7abf04fb0f56400559384b7993c97fa882",
        "6a265823b410ac4bdb6e869bb82b660e2af14b62c73b7261943d62a1b11eb44e",
        "09afe3b7b87bff3d1343f23af76391786719685df28103eb0a8200711525b38f",
    )
    actual_digests = tuple(
        hashlib.sha256(
            json.dumps(
                sorted((dict(row) for row in rows), key=lambda row: next(iter(row.values()))), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        for rows in collections
    )
    assert actual_digests == expected_digests
    assert next(row for row in ROAD_EDGES if row["edge_id"] == "E23") == {
        "edge_id": "E23",
        "name": "冷链中心国道线",
        "from_node_id": "N14",
        "to_node_id": "N07",
        "distance_km": "2.50",
        "base_minutes": 5,
        "road_level": "COUNTY",
        "risk_level": "LOW",
        "weight_limit_tons": "8.00",
    }
    assert {row["order_no"] for row in ORDERS} == {f"DEMO-ORDER-{number:03d}" for number in range(1, 13)}
