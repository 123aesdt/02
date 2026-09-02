import os
from uuid import uuid4

import pytest
from langgraph.graph import END, START, StateGraph
from redis.asyncio import Redis

from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore

pytestmark = pytest.mark.skipif(
    os.environ.get("COUNTYFLOW_REAL_CHECKPOINT_TEST") != "1",
    reason="set COUNTYFLOW_REAL_CHECKPOINT_TEST=1 with Docker Redis 8 running",
)


@pytest.mark.asyncio
async def test_official_saver_real_redis_round_trip_history_and_resume():
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")
    client = Redis.from_url(redis_url, decode_responses=False)
    info = await client.info("server")
    assert str(info["redis_version"]).startswith("8.")
    store = await RedisRuntimeCheckpointStore.from_url(
        redis_url,
        ttl_minutes=5,
        refresh_on_read=False,
        namespace="countyflow:test",
    )
    thread_id = f"cf:real-checkpoint:{uuid4().hex}"

    async def first(state: dict[str, int]):
        return {"value": state["value"] + 1}

    async def second(state: dict[str, int]):
        return {"value": state["value"] + 1}

    builder = StateGraph(dict)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    graph = builder.compile(checkpointer=store.native_checkpointer, interrupt_after=["first"])
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        await store.setup()
        interrupted = await graph.ainvoke({"value": 0}, config=config, durability="sync")
        history = await store.list_bounded(thread_id, 10)
        exact = await store.get_exact(thread_id, history[0].checkpoint_id)
        resumed = await graph.ainvoke(None, config=history[0].config, durability="sync")

        assert interrupted["value"] == 1
        assert exact is not None
        assert len(history) >= 2
        assert resumed["value"] == 2
    finally:
        await store.delete_thread(thread_id)
        await store.close()
        await client.aclose()


@pytest.mark.asyncio
async def test_redis8_existing_streams_regression():
    redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")
    client = Redis.from_url(redis_url, decode_responses=False)
    suffix = uuid4().hex
    stream = f"countyflow:test:streams:{suffix}"
    group = f"group-{suffix}"
    lock = f"countyflow:lock:dispatch:{suffix}"
    dlq = f"countyflow:dispatch:dlq:{suffix}"
    try:
        assert await client.ping() is True
        message_id = await client.xadd(stream, {"data": "payload"})
        await client.xgroup_create(stream, group, id="0", mkstream=True)
        delivered = await client.xreadgroup(group, "worker-1", {stream: ">"}, count=1)
        assert delivered
        pending = await client.xpending(stream, group)
        assert pending["pending"] == 1
        claimed = await client.xautoclaim(stream, group, "worker-2", 0, "0-0", count=1)
        assert claimed[1]
        await client.xadd(dlq, {"source_message_id": message_id})
        assert await client.xack(stream, group, message_id) == 1
        assert await client.set(lock, "token", nx=True, px=5_000) is True
        released = await client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            lock,
            "token",
        )
        assert released == 1
        assert (await client.xpending(stream, group))["pending"] == 0
    finally:
        await client.delete(stream, dlq, lock)
        await client.aclose()
