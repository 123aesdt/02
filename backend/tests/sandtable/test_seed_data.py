import hashlib
import json
from types import MappingProxyType

from app.sandtable.seed_data import DRIVERS, ORDERS, ROAD_EDGES, ROAD_NODES, STATIONS, VEHICLES


def test_new_county_seed_has_the_approved_inventory() -> None:
    assert (len(STATIONS), len(ROAD_NODES), len(ROAD_EDGES)) == (12, 22, 36)
    assert (len(DRIVERS), len(VEHICLES), len(ORDERS)) == (12, 20, 12)
    assert all(isinstance(row, MappingProxyType) for rows in (STATIONS, ROAD_NODES, ROAD_EDGES, DRIVERS, VEHICLES, ORDERS) for row in rows)
    edge = next(item for item in ROAD_EDGES if item["edge_id"] == "E04")
    vehicle = next(item for item in VEHICLES if item["vehicle_id"] == "V-005")
    assert (edge["from_node_id"], edge["to_node_id"], edge["distance_km"], edge["base_minutes"]) == ("N04", "N05", "2.50", 5)
    assert (vehicle["cargo_capability"], vehicle["max_load_kg"], vehicle["current_load_kg"]) == ("COLD_CHAIN", "1000.00", "100.00")


def test_all_approved_rows_match_the_business_id_sorted_contract() -> None:
    collections = (STATIONS, ROAD_NODES, ROAD_EDGES, DRIVERS, VEHICLES, ORDERS)
    expected_digests = (
        "0956aa72e38ddc0d18a5fd85888c3e397dc139fd3dcbac31bcfa545204a0895c",
        "096abc4e1e12c04dca148d615bde6d9c2ba8b4068cba8f58c3a4a3bc0a9e715a",
        "7ac536928deb99f52af18140a0b4214a85600e65a49443171093324baf8bb87d",
        "f6761637fca3026cc18170bad0572157fb897a45e5093d907881a82fd3099703",
        "398886486afb6e9d8b71986f9a35a33c2296ea3bd1d67d5c41930695e5c9eaea",
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
