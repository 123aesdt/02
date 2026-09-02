import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore
from app.runtime_threads.models import RuntimeThreadEventSnapshot, RuntimeThreadEventType, RuntimeThreadSnapshot, RuntimeThreadStatus
from app.runtime_threads.service import ThreadStateService
from app.security.permissions import Role
from tests.security_support import principal_for


class _Serializer:
    def __init__(self):
        self.values: list[object] = []

    def dumps_typed(self, value: object) -> tuple[str, bytes]:
        self.values.append(value)
        return "json", json.dumps(value, sort_keys=True).encode()


class _Saver:
    def __init__(self, tuples=()):
        self.serde = _Serializer()
        self.tuples = list(tuples)
        self.get_configs: list[dict[str, object]] = []
        self.list_configs: list[tuple[dict[str, object], int | None]] = []
        self.setup_calls = 0
        self.deleted: list[str] = []

    async def asetup(self):
        self.setup_calls += 1

    async def aget_tuple(self, config):
        self.get_configs.append(config)
        requested = config["configurable"].get("checkpoint_id")
        return next((item for item in self.tuples if item.config["configurable"]["checkpoint_id"] == requested), None)

    async def alist(self, config, *, limit=None):
        self.list_configs.append((config, limit))
        for item in self.tuples[:limit]:
            yield item

    async def adelete_thread(self, thread_id):
        self.deleted.append(thread_id)


def _tuple(checkpoint_id: str, parent_id: str | None = None):
    thread_id = "cf:dispatch:TASK-0123456789abcdef0123456789abcde"
    return SimpleNamespace(
        config={
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
            }
        },
        checkpoint={"id": checkpoint_id, "channel_values": {"last_completed_node": "intake"}},
        metadata={"source": "loop", "step": 1},
        parent_config=(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None
        ),
    )


@pytest.mark.asyncio
async def test_checkpoint_store_exact_read_never_falls_back_to_latest():
    saver = _Saver([_tuple("checkpoint-new"), _tuple("checkpoint-old")])
    store = RedisRuntimeCheckpointStore(saver)

    record = await store.get_exact(
        "cf:dispatch:TASK-0123456789abcdef0123456789abcde",
        "checkpoint-missing",
    )

    assert record is None
    assert saver.get_configs == [
        {
            "configurable": {
                "thread_id": "cf:dispatch:TASK-0123456789abcdef0123456789abcde",
                "checkpoint_ns": "",
                "checkpoint_id": "checkpoint-missing",
            }
        }
    ]


@pytest.mark.asyncio
async def test_checkpoint_store_history_is_bounded_and_safe():
    saver = _Saver([_tuple("checkpoint-2", "checkpoint-1"), _tuple("checkpoint-1")])
    store = RedisRuntimeCheckpointStore(saver)

    records = await store.list_bounded("cf:dispatch:TASK-0123456789abcdef0123456789abcde", 1)

    assert len(records) == 1
    assert records[0].checkpoint_id == "checkpoint-2"
    assert records[0].parent_checkpoint_id == "checkpoint-1"
    assert saver.list_configs[0][1] == 1
    json.dumps(asdict(records[0]))
    assert all(value is not saver for value in asdict(records[0]).values())


def test_checkpoint_size_uses_saver_serializer():
    saver = _Saver()
    store = RedisRuntimeCheckpointStore(saver)
    checkpoint = {"id": "checkpoint-1", "channel_values": {"value": "雨天"}}

    size = store.serialized_size(checkpoint)

    assert saver.serde.values == [checkpoint]
    assert size == len(b"json") + len(json.dumps(checkpoint, sort_keys=True).encode())


@pytest.mark.asyncio
async def test_checkpoint_store_setup_is_once_and_delete_is_narrow():
    saver = _Saver()
    store = RedisRuntimeCheckpointStore(saver)

    await store.setup()
    await store.setup()
    await store.delete_thread("cf:dispatch:TASK-0123456789abcdef0123456789abcde")

    assert saver.setup_calls == 1
    assert saver.deleted == ["cf:dispatch:TASK-0123456789abcdef0123456789abcde"]


def _runtime_thread():
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return RuntimeThreadSnapshot(
        thread_id="cf:dispatch:TASK-6123456789abcdef0123456789abcde",
        task_id="TASK-6123456789abcdef0123456789abcde",
        status=RuntimeThreadStatus.STABLE,
        current_checkpoint_id="checkpoint-1",
        state_version=1,
        current_node="intake",
        next_node="entity_memory",
        checkpoint_count=1,
        checkpoint_size_bytes=512,
        last_event_sequence=7,
        worker_consumer="worker-1",
        resumed_count=0,
        created_at=now,
        updated_at=now,
        terminal_at=None,
        row_version=1,
    )


class _ThreadRepository:
    def __init__(self, thread, events=()):
        self.thread = thread
        self.events = list(events)

    def get_by_thread_id(self, thread_id):
        return self.thread if thread_id == self.thread.thread_id else None

    def get_by_task_id(self, task_id):
        return self.thread if task_id == self.thread.task_id else None

    def list_events(self, thread_id, limit):
        return self.events[-limit:]


class _CheckpointStore:
    def __init__(self, records):
        self.records = {record.checkpoint_id: record for record in records}
        self.requested = []

    async def get_exact(self, thread_id, checkpoint_id):
        self.requested.append(checkpoint_id)
        return self.records.get(checkpoint_id)


@pytest.mark.asyncio
async def test_current_state_uses_canonical_pointer_not_latest_orphan():
    canonical = _tuple("checkpoint-1")
    orphan = _tuple("checkpoint-2", "checkpoint-1")
    saver = _Saver([orphan, canonical])
    redis_store = RedisRuntimeCheckpointStore(saver)
    canonical_record = redis_store._to_record(canonical)
    orphan_record = redis_store._to_record(orphan)
    store = _CheckpointStore([orphan_record, canonical_record])
    service = ThreadStateService(_ThreadRepository(_runtime_thread()), store)

    detail = await service.get_current_by_thread(_runtime_thread().thread_id, principal_for(Role.OPERATOR))

    assert detail["current_checkpoint_id"] == "checkpoint-1"
    assert detail["state"]["last_completed_node"] == "intake"
    assert store.requested == ["checkpoint-1"]


@pytest.mark.asyncio
async def test_canonical_history_is_version_ordered_and_bounded():
    from datetime import UTC, datetime

    thread = _runtime_thread()
    events = [
        RuntimeThreadEventSnapshot(
            event_id=f"event-{version}",
            event_key=f"checkpoint:{checkpoint_id}",
            thread_id=thread.thread_id,
            event_type=RuntimeThreadEventType.CHECKPOINT_PROMOTED,
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=None if version == 1 else f"checkpoint-{version - 1}",
            state_version=version,
            node="intake" if version == 1 else "entity_memory",
            next_node="entity_memory" if version == 1 else "graph_memory",
            checkpoint_size_bytes=512,
            worker_consumer="worker-1",
            error_code=None,
            metadata={},
            created_at=datetime.now(UTC),
        )
        for version, checkpoint_id in ((1, "checkpoint-1"), (2, "checkpoint-2"))
    ]
    records = [RedisRuntimeCheckpointStore(_Saver())._to_record(_tuple(f"checkpoint-{version}")) for version in (1, 2)]
    service = ThreadStateService(_ThreadRepository(thread, events), _CheckpointStore(records))

    history = await service.list_history(thread.thread_id, principal_for(Role.OPERATOR), limit=1)

    assert len(history["items"]) == 1
    assert history["items"][0]["state_version"] == 2
    assert history["items"][0]["checkpoint_id"] == "checkpoint-2"
