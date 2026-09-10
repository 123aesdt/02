from collections.abc import Callable, Mapping
from inspect import isawaitable
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.audit import audit_node
from app.agents.capacity import capacity_node
from app.agents.dispatch import dispatch_node
from app.agents.environment import environment_node
from app.agents.graph_memory import graph_memory_node
from app.agents.intake import intake_node
from app.agents.memory import entity_memory_node
from app.agents.routing import routing_node
from app.graph.dependencies import GraphDependencies
from app.graph.state import DispatchGraphState
from app.observability.recorder import MetricsRecorder, NoOpMetricsRecorder

NODE_ORDER = (
    "intake",
    "entity_memory",
    "graph_memory",
    "environment",
    "capacity",
    "routing",
    "dispatch",
    "audit",
)


def _instrument_node(
    name: str,
    node: Callable[[DispatchGraphState], Mapping[str, object] | Any],
    metrics: MetricsRecorder | None = None,
):
    recorder = metrics or NoOpMetricsRecorder()

    async def instrumented(state: DispatchGraphState) -> dict[str, object]:
        started = perf_counter()
        recorder.adjust_gauge("countyflow_agent_inflight", 1, {"agent": name})
        try:
            result = node(state)
            if isawaitable(result):
                result = await result
            patch = dict(result)
            elapsed = perf_counter() - started
            _record_node_metrics(name, patch, elapsed, recorder)
            recorder.observe_agent(name, _agent_result(patch), elapsed)
            return {
                **patch,
                "last_completed_node": name,
                "completed_node_count": state.get("completed_node_count", 0) + 1,
            }
        except BaseException as error:
            result = "cancelled" if error.__class__.__name__ == "CancelledError" else "error"
            recorder.observe_agent(name, result, perf_counter() - started)
            raise
        finally:
            recorder.adjust_gauge("countyflow_agent_inflight", -1, {"agent": name})

    instrumented.__name__ = name
    return instrumented


def _agent_result(patch: Mapping[str, object]) -> str:
    if patch.get("requires_manual_review") is True:
        return "review_required"
    if patch.get("error_code") or patch.get("fallback_used") is True or patch.get("graph_memory_error"):
        return "degraded"
    return "success"


def _record_node_metrics(name: str, patch: Mapping[str, object], elapsed: float, metrics: MetricsRecorder) -> None:
    if name == "entity_memory":
        result = "error" if patch.get("error_code") == "MEMORY_RECALL_ERROR" else "hit" if patch.get("memory_results") else "miss"
        metrics.increment("countyflow_vector_recall_total", {"result": result})
        metrics.observe("countyflow_vector_recall_duration_seconds", elapsed)
    elif name == "graph_memory":
        result = "error" if patch.get("graph_memory_error") else "success" if patch.get("graph_memory_used") else "empty"
        seconds = float(patch.get("graph_memory_elapsed_ms") or elapsed * 1000) / 1000
        metrics.increment("countyflow_graph_queries_total", {"operation": "multi_hop", "result": result})
        metrics.observe("countyflow_graph_query_duration_seconds", seconds, {"operation": "multi_hop"})
        if result == "error":
            metrics.increment("countyflow_graph_memory_degraded_total", {"reason_code": "query_error"})
    elif name == "environment":
        fallback = patch.get("fallback_used") is True
        metrics.increment("countyflow_environment_requests_total", {"operation": "primary", "result": "error" if fallback else "success"})
        metrics.observe("countyflow_environment_duration_seconds", elapsed, {"operation": "primary"})
        if fallback:
            reason = str(patch.get("fallback_reason") or "").lower()
            reason_code = "circuit_open" if "circuit" in reason else "timeout" if "timed out" in reason else "http_error"
            metrics.increment("countyflow_environment_fallback_total", {"reason_code": reason_code})
            metrics.increment("countyflow_environment_requests_total", {"operation": "fallback", "result": "success"})


def build_graph(
    dependencies: GraphDependencies | None = None,
    *,
    checkpointer=None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
):
    audit_service = dependencies.audit_service if dependencies else None
    capacity_service = dependencies.capacity_service if dependencies else None
    dispatch_service = dependencies.dispatch_service if dependencies else None
    entity_memory_service = dependencies.entity_memory_service if dependencies else None
    graph_memory_service = dependencies.graph_memory_service if dependencies else None
    environment_service = dependencies.environment_service if dependencies else None
    routing_service = dependencies.routing_service if dependencies else None
    sandtable_context_service = dependencies.sandtable_context_service if dependencies else None
    fleet_allocation_service = dependencies.fleet_allocation_service if dependencies else None
    road_network_snapshot_service = dependencies.road_network_snapshot_service if dependencies else None
    issue_recommendation_service = dependencies.issue_recommendation_service if dependencies else None
    metrics = dependencies.metrics if dependencies else NoOpMetricsRecorder()

    async def entity_memory(state: DispatchGraphState) -> dict[str, object]:
        return await entity_memory_node(state, entity_memory_service)

    async def environment(state: DispatchGraphState) -> dict[str, object]:
        return await environment_node(state, environment_service)

    async def graph_memory(state: DispatchGraphState) -> dict[str, object]:
        return await graph_memory_node(state, graph_memory_service)

    async def capacity(state: DispatchGraphState) -> dict[str, object]:
        return await capacity_node(state, capacity_service, fleet_allocation_service, road_network_snapshot_service)

    async def routing(state: DispatchGraphState) -> dict[str, object]:
        return await routing_node(state, routing_service, issue_recommendation_service, road_network_snapshot_service)

    async def dispatch(state: DispatchGraphState) -> dict[str, object]:
        return await dispatch_node(state, dispatch_service)

    async def audit(state: DispatchGraphState) -> dict[str, object]:
        return await audit_node(state, audit_service)

    graph = StateGraph(DispatchGraphState)
    graph.add_node(
        "intake",
        _instrument_node(
            "intake",
            lambda state: intake_node(state, sandtable_context_service, road_network_snapshot_service),
            metrics,
        ),
    )
    graph.add_node("entity_memory", _instrument_node("entity_memory", entity_memory, metrics))
    graph.add_node("graph_memory", _instrument_node("graph_memory", graph_memory, metrics))
    graph.add_node("environment", _instrument_node("environment", environment, metrics))
    graph.add_node("capacity", _instrument_node("capacity", capacity, metrics))
    graph.add_node("routing", _instrument_node("routing", routing, metrics))
    graph.add_node("dispatch", _instrument_node("dispatch", dispatch, metrics))
    graph.add_node("audit", _instrument_node("audit", audit, metrics))
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "entity_memory")
    graph.add_edge("entity_memory", "graph_memory")
    graph.add_edge("graph_memory", "environment")
    graph.add_edge("environment", "capacity")
    graph.add_edge("capacity", "routing")
    graph.add_edge("routing", "dispatch")
    graph.add_edge("dispatch", "audit")
    graph.add_edge("audit", END)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
    )
