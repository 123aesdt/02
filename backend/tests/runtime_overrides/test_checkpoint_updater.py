from typing import NotRequired, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.runtime_overrides.checkpoint_updater import LangGraphStateUpdater
from app.runtime_threads.checkpoint_store import RedisRuntimeCheckpointStore


class State(TypedDict):
    vehicle_id: str
    vehicle_status: str
    last_completed_node: NotRequired[str]
    completed_node_count: NotRequired[int]


def graph_with_environment_boundary(saver: InMemorySaver):
    def environment(state: State):
        return {"last_completed_node": "environment", "completed_node_count": 1}

    def capacity(state: State):
        return {"last_completed_node": "capacity", "completed_node_count": 2}

    graph = StateGraph(State)
    graph.add_node("environment", environment)
    graph.add_node("capacity", capacity)
    graph.add_edge(START, "environment")
    graph.add_edge("environment", "capacity")
    graph.add_edge("capacity", END)
    return graph.compile(checkpointer=saver, interrupt_after=["environment"])


@pytest.mark.asyncio
async def test_runtime_override_updates_checkpoint() -> None:
    saver = InMemorySaver()
    graph = graph_with_environment_boundary(saver)
    store = RedisRuntimeCheckpointStore(saver)
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    await graph.ainvoke({"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}, config)
    source_snapshot = await graph.aget_state(config)
    source_id = source_snapshot.config["configurable"]["checkpoint_id"]
    source = await store.get_exact("thread-1", source_id)
    assert source is not None

    updated = await LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576).update(
        source,
        {"vehicle_status": "BROKEN"},
        as_node="environment",
        expected_next_node="capacity",
        override_id="override-1",
    )

    assert updated.record.parent_checkpoint_id == source.checkpoint_id
    assert updated.next_nodes == ("capacity",)
    assert updated.record.state["vehicle_status"] == "BROKEN"
    assert updated.record.state["completed_node_count"] == 1


@pytest.mark.asyncio
async def test_runtime_override_rejects_protected_state_diff() -> None:
    saver = InMemorySaver()
    graph = graph_with_environment_boundary(saver)
    store = RedisRuntimeCheckpointStore(saver)
    config = {"configurable": {"thread_id": "thread-2", "checkpoint_ns": ""}}
    await graph.ainvoke({"vehicle_id": "vehicle-001", "vehicle_status": "NORMAL"}, config)
    snapshot = await graph.aget_state(config)
    source = await store.get_exact("thread-2", snapshot.config["configurable"]["checkpoint_id"])
    assert source is not None

    with pytest.raises(ValueError, match="STATE_DIFF_NOT_ALLOWED"):
        await LangGraphStateUpdater(graph, store, max_checkpoint_bytes=1_048_576).update(
            source,
            {"vehicle_status": "BROKEN", "vehicle_id": "vehicle-999"},
            as_node="environment",
            expected_next_node="capacity",
            override_id="override-2",
        )
