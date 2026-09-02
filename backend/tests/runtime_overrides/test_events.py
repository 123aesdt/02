from dataclasses import replace

import pytest

from app.events.broker import InMemoryTaskEventBroker
from app.events.models import TaskEventType
from app.runtime_overrides.events import RuntimeOverrideEventPublisher

from .test_service import request, service_fixture


@pytest.mark.asyncio
async def test_runtime_override_event(sqlite_factory) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    applied = await service.apply("thread-override", request())
    broker = InMemoryTaskEventBroker()
    publisher = RuntimeOverrideEventPublisher(broker)

    first = await publisher.publish_applied(applied)
    second = await publisher.publish_applied(applied)

    assert first.event_type is TaskEventType.RUNTIME_OVERRIDE_APPLIED
    assert second.event_id == first.event_id
    history = await broker.history(applied.task_id)
    assert len(history) == 1
    assert history[0].data == {
        "override_id": applied.override_id,
        "thread_id": applied.thread_id,
        "operator_id": applied.operator_id,
        "operator_role": applied.operator_role,
        "status": "APPLIED",
        "expected_version": applied.expected_version,
        "expected_next_node": applied.expected_next_node,
        "source_checkpoint_id": applied.source_checkpoint_id,
        "result_checkpoint_id": applied.result_checkpoint_id,
        "before_state_version": applied.before_state_version,
        "after_state_version": applied.after_state_version,
        "entity_type": applied.entity_type,
        "entity_id": applied.entity_id,
        "field": applied.field,
        "old_value": applied.old_value,
        "new_value": applied.new_value,
        "reason": applied.reason,
        "error_code": None,
    }
    for forbidden in (
        "idempotency_key",
        "payload_fingerprint",
        "operator_permissions",
        "token",
        "checkpoint_state",
        "checkpoint_payload",
    ):
        assert forbidden not in history[0].data


@pytest.mark.asyncio
async def test_runtime_override_events_publish_once_per_type(sqlite_factory) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    applied = await service.apply("thread-override", request())
    broker = InMemoryTaskEventBroker()
    publisher = RuntimeOverrideEventPublisher(broker)

    requested = await publisher.publish_requested(applied)
    repeated = await publisher.publish_requested(applied)

    assert requested.event_type is TaskEventType.RUNTIME_OVERRIDE_REQUESTED
    assert repeated.event_id == requested.event_id
    assert len(await broker.history(applied.task_id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "event_type"),
    [
        ("REJECTED", TaskEventType.RUNTIME_OVERRIDE_REJECTED),
        ("CONFLICT", TaskEventType.RUNTIME_OVERRIDE_CONFLICT),
        ("PARTIAL", TaskEventType.RUNTIME_OVERRIDE_PARTIAL),
    ],
)
async def test_runtime_override_non_applied_events_are_safe(sqlite_factory, status, event_type) -> None:
    service, _, _, _ = await service_fixture(sqlite_factory)
    applied = await service.apply("thread-override", request())
    item = replace(applied, status=type(applied.status)(status), error_code="SAFE_DOMAIN_CODE")
    broker = InMemoryTaskEventBroker()

    event = await RuntimeOverrideEventPublisher(broker).publish_status(item)

    assert event.event_type is event_type
    assert event.data["status"] == status
    assert event.data["error_code"] == "SAFE_DOMAIN_CODE"
    assert event.data["operator_id"] == applied.operator_id
    assert event.data["reason"] == applied.reason
