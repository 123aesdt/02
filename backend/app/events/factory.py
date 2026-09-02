from app.core.config import Settings
from app.events.broker import InMemoryTaskEventBroker, RedisTaskEventBroker


def create_task_event_broker(settings: Settings, redis_client: object):
    if settings.task_event_broker == "redis":
        return RedisTaskEventBroker(
            redis_client,
            settings.task_event_stream_prefix,
            settings.task_event_history_maxlen,
            read_block_ms=settings.task_event_block_ms,
        )
    return InMemoryTaskEventBroker(history_size=settings.task_event_history_maxlen)
