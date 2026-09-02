from app.events.models import TaskEvent, TaskEventType

SAFE_EVENT_FIELDS = frozenset(
    {
        "mutation_id",
        "fact_key",
        "decision",
        "status",
        "before_version",
        "after_version",
        "vector_status",
        "graph_status",
    }
)


class MemoryMutationEventPublisher:
    def __init__(self, broker: object) -> None:
        self._broker = broker

    async def publish(self, event_type: str, payload: dict[str, object]) -> None:
        mutation_id = str(payload["mutation_id"])
        safe_payload = {key: value for key, value in payload.items() if key in SAFE_EVENT_FIELDS}
        await self._broker.publish(
            TaskEvent.create(
                mutation_id,
                TaskEventType(event_type),
                "shared_memory",
                str(payload.get("status") or "REQUESTED"),
                data=safe_payload,
            )
        )
