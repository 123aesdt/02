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
