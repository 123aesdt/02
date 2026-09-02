from app.events.models import TaskEvent, TaskEventType


class RuntimeOverrideEventPublisher:
    def __init__(self, broker) -> None:
        self._broker = broker
        self._published: dict[tuple[str, TaskEventType], TaskEvent] = {}

    async def publish_applied(self, item) -> TaskEvent:
        return await self._publish(item, TaskEventType.RUNTIME_OVERRIDE_APPLIED, "APPLIED")

    async def publish_requested(self, item) -> TaskEvent:
        return await self._publish(item, TaskEventType.RUNTIME_OVERRIDE_REQUESTED, "PENDING")

    async def publish_status(self, item) -> TaskEvent:
        event_type = {
            "REJECTED": TaskEventType.RUNTIME_OVERRIDE_REJECTED,
            "CONFLICT": TaskEventType.RUNTIME_OVERRIDE_CONFLICT,
            "PARTIAL": TaskEventType.RUNTIME_OVERRIDE_PARTIAL,
        }.get(item.status.value, TaskEventType.RUNTIME_OVERRIDE_REQUESTED)
        return await self._publish(item, event_type, item.status.value)

    async def _publish(self, item, event_type: TaskEventType, status: str) -> TaskEvent:
        identity = (item.override_id, event_type)
        existing = self._published.get(identity)
        if existing is not None:
            return existing
        event = TaskEvent.create(
            item.task_id,
            event_type,
            "runtime_override",
            status,
            data={
                "override_id": item.override_id,
                "thread_id": item.thread_id,
                "operator_id": item.operator_id,
                "operator_role": item.operator_role,
                "status": status,
                "expected_version": item.expected_version,
                "expected_next_node": item.expected_next_node,
                "source_checkpoint_id": item.source_checkpoint_id,
                "result_checkpoint_id": item.result_checkpoint_id,
                "before_state_version": item.before_state_version,
                "after_state_version": item.after_state_version,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "field": item.field,
                "old_value": item.old_value,
                "new_value": item.new_value,
                "reason": item.reason,
                "error_code": item.error_code,
            },
        )
        published = await self._broker.publish(event)
        self._published[identity] = published
        return published
