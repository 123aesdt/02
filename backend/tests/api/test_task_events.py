import asyncio
from datetime import UTC, datetime

import pytest

from app.events.broker import InMemoryTaskEventBroker
from app.events.graph_adapter import GraphEventAdapter
from app.events.models import TaskEvent, TaskEventType


def test_task_event_serialization():
    event = TaskEvent.create(
        task_id="TASK-001",
        event_type=TaskEventType.WORKER_STARTED,
        node="worker",
        status="PROCESSING",
        sequence=1,
        data={"consumer_name": "worker-1", "message_id": "1-0"},
    )

    payload = event.to_dict()
    assert payload["task_id"] == "TASK-001"
    assert payload["event_type"] == "WORKER_STARTED"
    assert payload["sequence"] == 1
    assert datetime.fromisoformat(payload["timestamp"]).tzinfo == UTC


@pytest.mark.asyncio
async def test_task_event_sequence_is_monotonic():
    broker = InMemoryTaskEventBroker()
    first = await broker.publish(TaskEvent.create("TASK-001", TaskEventType.TASK_ACCEPTED, "api", "PENDING"))
    second = await broker.publish(TaskEvent.create("TASK-001", TaskEventType.WORKER_STARTED, "worker", "PROCESSING"))

    assert (first.sequence, second.sequence) == (1, 2)


@pytest.mark.asyncio
async def test_slow_subscriber_drops_oldest_event_without_blocking_publish():
    broker = InMemoryTaskEventBroker(subscriber_queue_size=1)
    subscription = await broker.subscribe("TASK-001")
    await broker.publish(TaskEvent.create("TASK-001", TaskEventType.TASK_ACCEPTED, "api", "PENDING"))
    await asyncio.wait_for(
        broker.publish(TaskEvent.create("TASK-001", TaskEventType.WORKER_STARTED, "worker", "PROCESSING")),
        timeout=0.1,
    )

    event = subscription.queue.get_nowait()
    assert event.event_type == TaskEventType.WORKER_STARTED


@pytest.mark.asyncio
async def test_graph_event_adapter_maps_fallback_and_safe_routing_data():
    class StreamingGraph:
        async def astream(self, state, *, stream_mode):
            yield {"intake": {}}
            yield {"entity_memory": {}}
            yield {
                "graph_memory": {
                    "graph_memory_used": False,
                    "graph_memory_error": "Graph memory recall is temporarily unavailable.",
                    "graph_memory_elapsed_ms": 0.0,
                    "graph_memory_facts": [],
                    "graph_memory_paths": [],
                }
            }
            yield {
                "environment": {
                    "fallback_used": True,
                    "fallback_reason": "Primary environment provider timed out.",
                    "environment_elapsed_ms": 800,
                    "environment_risk": "high",
                }
            }
            yield {
                "capacity": {
                    "capacity_state": {
                        "driver_available": True,
                        "vehicle_available": False,
                        "capacity_status": "UNAVAILABLE",
                        "risk_level": "high",
                        "reason": "vehicle runtime status is BROKEN",
                    }
                }
            }
            yield {
                "routing": {
                    "recommended_route": "national-102",
                    "decision": "REVIEW_REQUIRED",
                    "decision_reason": "vehicle vehicle-001 is unavailable",
                    "memory_adopted": True,
                    "requires_manual_review": True,
                    "candidate_routes": [
                        {
                            "route_id": "national-102",
                            "route_name": "102国道",
                            "distance_km": 18.2,
                            "estimated_minutes": 34,
                            "risk_level": "low",
                            "available": True,
                            "reason": None,
                            "score": 92.0,
                        }
                    ],
                }
            }
            yield {"dispatch": {}}
            yield {"audit": {"audit_result": {"audit_status": "APPROVED"}}}

    broker = InMemoryTaskEventBroker()
    subscription = await broker.subscribe("TASK-001")
    await GraphEventAdapter(broker).invoke(
        StreamingGraph(),
        {"task_id": "TASK-001", "vehicle_id": "vehicle-001", "vehicle_status": "BROKEN"},
    )
    events = [subscription.queue.get_nowait().to_dict() for _ in range(subscription.queue.qsize())]

    fallback = next(event for event in events if event["event_type"] == "ENVIRONMENT_FALLBACK")
    degraded = next(event for event in events if event["event_type"] == "GRAPH_MEMORY_DEGRADED")
    routing = next(event for event in events if event["event_type"] == "ROUTING_COMPLETED")
    capacity = next(event for event in events if event["event_type"] == "CAPACITY_COMPLETED")
    audit = next(event for event in events if event["event_type"] == "AUDIT_COMPLETED")
    assert fallback["data"] == {
        "fallback_reason": "Primary environment provider timed out.",
        "environment_elapsed_ms": 800,
        "environment_risk": "high",
    }
    assert routing["data"] == {
        "recommended_route": "national-102",
        "decision": "REVIEW_REQUIRED",
        "decision_reason": "vehicle vehicle-001 is unavailable",
        "memory_adopted": True,
        "requires_manual_review": True,
        "candidate_routes": [
            {
                "route_id": "national-102",
                "route_name": "102国道",
                "distance_km": 18.2,
                "estimated_minutes": 34,
                "risk_level": "low",
                "available": True,
                "reason": None,
                "score": 92.0,
            }
        ],
    }
    assert capacity["data"] == {
        "vehicle_id": "vehicle-001",
        "vehicle_status": "BROKEN",
        "driver_available": True,
        "vehicle_available": False,
        "capacity_status": "UNAVAILABLE",
        "risk_level": "high",
        "reason": "vehicle runtime status is BROKEN",
    }
    assert degraded["data"] == {
        "graph_memory_used": False,
        "graph_memory_error": "Graph memory recall is temporarily unavailable.",
        "graph_memory_elapsed_ms": 0.0,
        "graph_memory_facts": [],
        "graph_memory_paths": [],
    }
    assert audit["data"] == {"audit_result": {"audit_status": "APPROVED"}}


@pytest.mark.asyncio
async def test_graph_event_adapter_projects_fleet_route_and_dispatch_snapshot_as_json_safe_data():
    import json
    from decimal import Decimal

    from app.sandtable.seed_data import VEHICLES

    candidate_vehicles = [
        {
            "vehicle_id": f"V-{index:03d}",
            "driver_id": "D-003" if index == 5 else None,
            "pickup_distance_km": Decimal("2.80") if index == 5 else None,
            "score": Decimal("93.4") if index == 5 else None,
            "eligible": index == 5,
            "exclusion_reasons": [] if index == 5 else ["NOT_SELECTED"],
        }
        for index in range(1, len(VEHICLES) + 1)
    ]

    class StreamingGraph:
        async def astream(self, state, *, stream_mode):
            yield {"intake": {}}
            yield {"entity_memory": {}}
            yield {"graph_memory": {}}
            yield {"environment": {}}
            yield {
                "capacity": {
                    "capacity_state": {
                        "driver_available": True,
                        "vehicle_available": True,
                        "capacity_status": "REASSIGNED",
                        "risk_level": "low",
                        "reason": None,
                    },
                    "candidate_vehicles": candidate_vehicles,
                    "selected_vehicle_id": "V-005",
                    "selected_driver_id": "D-003",
                    "vehicle_reassigned": True,
                    "pickup_route": {
                        "node_ids": ["N15", "N04"],
                        "edge_ids": ["E20"],
                        "distance_km": Decimal("2.80"),
                        "estimated_minutes": 6,
                    },
                }
            }
            yield {
                "routing": {
                    "blocked_edge_ids": ["E04"],
                    "original_path": {
                        "node_ids": ["N01", "N02", "N03", "N04", "N05", "N06"],
                        "edge_ids": ["E01", "E02", "E03", "E04", "E05"],
                        "distance_km": Decimal("10.00"),
                        "estimated_minutes": 20,
                    },
                    "recommended_path": {
                        "node_ids": ["N01", "N02", "N07", "N08", "N09", "N06"],
                        "edge_ids": ["E01", "E06", "E07", "E08", "E09"],
                        "distance_km": Decimal("13.20"),
                        "estimated_minutes": 24,
                        "visited_node_count": 8,
                    },
                    "candidate_routes": [],
                    "distance_delta_km": Decimal("3.20"),
                    "eta_delta_minutes": 4,
                    "routing_algorithm": "DIJKSTRA_V1",
                    "routing_status": "ROUTED",
                    "road_network_version": 7,
                    "road_network_nodes": [{"node_id": "N01", "name": "中心仓", "x_km": Decimal("0.00"), "y_km": Decimal("0.00"), "node_type": "STATION"}],
                    "road_network_edges": [
                        {
                            "edge_id": "E04",
                            "name": "新平路东河桥段",
                            "from_node_id": "N04",
                            "to_node_id": "N05",
                            "distance_km": Decimal("2.50"),
                            "base_minutes": 5,
                            "road_level": "COUNTY",
                            "risk_level": "HIGH",
                            "status": "BLOCKED",
                            "congestion_factor": Decimal("1.00"),
                            "weight_limit_tons": Decimal("6.00"),
                            "bidirectional": True,
                            "version": 2,
                        }
                    ],
                }
            }
            yield {
                "dispatch": {
                    "dispatch_result": {
                        "original_vehicle_id": "V-001",
                        "target_vehicle_id": "V-005",
                        "target_driver_id": "D-003",
                        "target_route_id": "RTE-RECOMMENDED",
                        "status": "REROUTED",
                        "version": 1,
                        "executed": True,
                    }
                }
            }
            yield {"audit": {}}

    broker = InMemoryTaskEventBroker()
    subscription = await broker.subscribe("TASK-007")
    await GraphEventAdapter(broker).invoke(
        StreamingGraph(),
        {"task_id": "TASK-007", "vehicle_id": "V-001", "vehicle_status": "BROKEN"},
    )
    events = [subscription.queue.get_nowait().to_dict() for _ in range(subscription.queue.qsize())]
    capacity = next(event for event in events if event["event_type"] == "CAPACITY_COMPLETED")
    routing = next(event for event in events if event["event_type"] == "ROUTING_COMPLETED")
    dispatch = next(event for event in events if event["event_type"] == "DISPATCH_COMPLETED")

    assert capacity["data"]["selected_vehicle_id"] == "V-005"
    assert capacity["data"]["selected_driver_id"] == "D-003"
    assert capacity["data"]["vehicle_reassigned"] is True
    assert len(capacity["data"]["candidate_vehicles"]) == len(VEHICLES)
    assert capacity["data"]["pickup_route"]["distance_km"] == "2.80"
    assert routing["data"]["algorithm"] == "DIJKSTRA_V1"
    assert routing["data"]["blocked_edge_ids"] == ["E04"]
    assert routing["data"]["recommended_path"]["edge_ids"] == ["E01", "E06", "E07", "E08", "E09"]
    assert routing["data"]["distance_delta_km"] == "3.20"
    assert routing["data"]["visited_node_count"] == 8
    assert routing["data"]["network_nodes"][0]["x_km"] == "0.00"
    assert routing["data"]["network_edges"][0]["weight_limit_tons"] == "6.00"
    assert dispatch["data"]["original_vehicle_id"] == "V-001"
    assert dispatch["data"]["target_vehicle_id"] == "V-005"
    assert dispatch["data"]["target_driver_id"] == "D-003"
    json.dumps(events)
