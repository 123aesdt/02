from prometheus_client import CollectorRegistry

from app.observability.catalog import build_metric_catalog
from app.observability.labels import FORBIDDEN_HIGH_CARDINALITY_LABELS, METRIC_LABEL_ALLOWLIST


def test_metric_catalog_uses_only_allowlisted_labels() -> None:
    catalog = build_metric_catalog(CollectorRegistry())

    assert {
        "countyflow_http_requests_total",
        "countyflow_agent_executions_total",
        "countyflow_graph_queries_total",
        "countyflow_checkpoint_operations_total",
        "countyflow_runtime_overrides_total",
        "countyflow_worker_messages_total",
    } <= catalog.family_names()
    for definition in catalog.definitions:
        assert set(definition.labels) <= METRIC_LABEL_ALLOWLIST
        assert FORBIDDEN_HIGH_CARDINALITY_LABELS.isdisjoint(definition.labels)


def test_metrics_registry_not_double_registered() -> None:
    registry = CollectorRegistry()

    first = build_metric_catalog(registry)
    second = build_metric_catalog(registry)

    assert first is second


def test_http_metrics_no_task_id_label() -> None:
    catalog = build_metric_catalog(CollectorRegistry())

    assert all("task_id" not in definition.labels for definition in catalog.definitions)
