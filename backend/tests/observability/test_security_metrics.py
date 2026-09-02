import json
from pathlib import Path

import yaml
from prometheus_client import CollectorRegistry, generate_latest

from app.observability.catalog import build_metric_catalog
from app.observability.recorder import PrometheusMetricsRecorder

ROOT = Path(__file__).resolve().parents[3]


def test_security_metrics_no_subject_label() -> None:
    registry = CollectorRegistry()
    catalog = build_metric_catalog(registry)
    recorder = PrometheusMetricsRecorder(catalog)
    expected = {
        "countyflow_authentication_failures_total",
        "countyflow_authorization_denied_total",
        "countyflow_rate_limit_exceeded_total",
        "countyflow_ws_ticket_rejected_total",
    }

    assert expected <= catalog.family_names()
    for name in expected:
        definition = catalog.definition(name)
        assert definition.labels == ("reason_code", "route_class")
        assert "subject_id" not in definition.labels
    recorder.increment(
        "countyflow_authorization_denied_total",
        {"reason_code": "permission", "route_class": "runtime"},
    )
    text = generate_latest(registry).decode()
    assert 'countyflow_authorization_denied_total{reason_code="permission",route_class="runtime"} 1.0' in text
    assert "subject" not in text


def test_security_alerts_have_volume_guards_and_duration() -> None:
    document = yaml.safe_load(
        (ROOT / "monitoring/prometheus/rules/countyflow-alerts.yml").read_text(encoding="utf-8")
    )
    rules = {rule["alert"]: rule for group in document["groups"] for rule in group["rules"]}
    expected = {
        "AuthenticationFailureSpike",
        "AuthorizationDeniedSpike",
        "RuntimeOverrideDeniedSpike",
        "RateLimitSpike",
        "WsTicketRejectionSpike",
    }
    assert expected <= rules.keys()
    for name in expected:
        assert "increase(" in rules[name]["expr"]
        assert rules[name]["for"]


def test_security_dashboard_is_provisioned() -> None:
    dashboard = json.loads(
        (ROOT / "monitoring/grafana/dashboards/countyflow-v2-security.json").read_text(encoding="utf-8")
    )

    assert dashboard["uid"] == "countyflow-v2-security"
    assert {panel["title"] for panel in dashboard["panels"]} >= {
        "Authentication Failures",
        "Authorization Denials",
        "Rate Limit Exceeded",
        "WebSocket Ticket Rejections",
    }
    serialized = json.dumps(dashboard)
    for forbidden in ("subject_id", "task_id", "remote_ip", "?ticket="):
        assert forbidden not in serialized
