import pytest
from prometheus_client import CollectorRegistry, generate_latest

from app.graph.builder import _instrument_node
from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder, SafeMetricsRecorder


def recorder_and_registry():
    registry = CollectorRegistry()
    return SafeMetricsRecorder(PrometheusMetricsRecorder(build_metric_catalog(registry))), registry


@pytest.mark.asyncio
async def test_vector_metrics() -> None:
    recorder, registry = recorder_and_registry()

    await _instrument_node("entity_memory", lambda state: {"memory_results": [{"memory_id": "hidden"}]}, recorder)({})

    text = generate_latest(registry).decode()
    assert 'countyflow_vector_recall_total{result="hit"} 1.0' in text
    assert "hidden" not in text
    assert "countyflow_vector_recall_duration_seconds_count 1.0" in text


@pytest.mark.asyncio
async def test_graph_metrics() -> None:
    recorder, registry = recorder_and_registry()

    await _instrument_node(
        "graph_memory",
        lambda state: {"graph_memory_used": False, "graph_memory_error": "safe degradation", "graph_memory_elapsed_ms": 12.5},
        recorder,
    )({})

    text = generate_latest(registry).decode()
    assert 'countyflow_graph_queries_total{operation="multi_hop",result="error"} 1.0' in text
    assert 'countyflow_graph_memory_degraded_total{reason_code="query_error"} 1.0' in text
    assert "safe degradation" not in text
