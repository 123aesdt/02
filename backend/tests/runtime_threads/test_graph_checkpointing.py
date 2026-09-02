import json
from collections.abc import Mapping, Sequence

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.builder import build_graph


def _state() -> dict[str, object]:
    return {
        "task_id": "TASK-0123456789abcdef0123456789abcde",
        "order_id": 1,
        "driver_id": "driver-1",
        "route_id": "route-1",
        "anomaly_type": "road_risk",
        "anomaly_description": "雨天道路湿滑",
    }


def _config(thread_id: str = "cf:dispatch:TASK-0123456789abcdef0123456789abcde") -> dict[str, object]:
    return {"configurable": {"thread_id": thread_id}}


@pytest.mark.asyncio
async def test_checkpoint_after_node():
    saver = InMemorySaver()
    graph = build_graph(checkpointer=saver, interrupt_after=["intake"])

    result = await graph.ainvoke(_state(), config=_config(), durability="sync")
    checkpoint = await saver.aget_tuple(_config())

    assert result["last_completed_node"] == "intake"
    assert result["completed_node_count"] == 1
    assert checkpoint is not None
    assert checkpoint.checkpoint["channel_values"]["last_completed_node"] == "intake"
    assert checkpoint.checkpoint["channel_values"]["completed_node_count"] == 1
    assert checkpoint.checkpoint["channel_values"]["branch:to:entity_memory"] is None


@pytest.mark.asyncio
async def test_checkpoint_payload_serializable():
    saver = InMemorySaver()
    graph = build_graph(checkpointer=saver, interrupt_after=["intake"])
    await graph.ainvoke(_state(), config=_config("cf:dispatch:TASK-1123456789abcdef0123456789abcde"))

    checkpoint = await saver.aget_tuple(_config("cf:dispatch:TASK-1123456789abcdef0123456789abcde"))

    assert checkpoint is not None
    for value in checkpoint.checkpoint["channel_values"].values():
        json.dumps(value)


def _walk_values(value: object):
    yield value
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            yield from _walk_values(nested)


@pytest.mark.asyncio
async def test_checkpoint_excludes_dependencies():
    saver = InMemorySaver()
    graph = build_graph(checkpointer=saver, interrupt_after=["intake"])
    await graph.ainvoke(_state(), config=_config("cf:dispatch:TASK-2123456789abcdef0123456789abcde"))
    checkpoint = await saver.aget_tuple(_config("cf:dispatch:TASK-2123456789abcdef0123456789abcde"))

    assert checkpoint is not None
    forbidden_modules = ("redis", "sqlalchemy", "qdrant", "neo4j", "app.runtime_threads")
    for value in _walk_values(checkpoint.checkpoint["channel_values"]):
        value_type = type(value)
        assert not value_type.__module__.startswith(forbidden_modules)
        assert not isinstance(value, type)
