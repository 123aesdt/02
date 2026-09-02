import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_compose_declares_exactly_eleven_services_and_internal_metric_targets() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert len(compose["services"]) == 11
    assert {"prometheus", "grafana"} <= compose["services"].keys()
    for service in ("backend", "worker-1", "worker-2"):
        assert "9100:9100" not in compose["services"][service].get("ports", [])


def test_prometheus_scrapes_three_processes_and_loads_rules() -> None:
    config = yaml.safe_load((ROOT / "monitoring/prometheus/prometheus.yml").read_text(encoding="utf-8"))
    assert config["global"] == {"scrape_interval": "15s", "scrape_timeout": "5s"}
    jobs = {item["job_name"]: item["static_configs"][0]["targets"] for item in config["scrape_configs"]}
    assert jobs == {"backend": ["backend:9100"], "worker-1": ["worker-1:9100"], "worker-2": ["worker-2:9100"]}
    assert config["rule_files"]


def test_dashboard_and_datasource_are_provisioned_without_manual_steps() -> None:
    datasource = yaml.safe_load((ROOT / "monitoring/grafana/provisioning/datasources/prometheus.yml").read_text(encoding="utf-8"))
    dashboard = json.loads((ROOT / "monitoring/grafana/dashboards/countyflow-v2-operations.json").read_text(encoding="utf-8"))
    assert datasource["datasources"][0]["uid"] == "countyflow-prometheus"
    assert datasource["datasources"][0]["url"] == "http://prometheus:9090"
    assert dashboard["uid"] == "countyflow-v2-operations"
    assert len({panel["title"] for panel in dashboard["panels"]}) >= 9


def test_alert_rules_include_required_slo_and_invariant_guards() -> None:
    alerts = yaml.safe_load((ROOT / "monitoring/prometheus/rules/countyflow-alerts.yml").read_text(encoding="utf-8"))
    rules = [rule for group in alerts["groups"] for rule in group["rules"]]
    names = {rule["alert"] for rule in rules}
    assert {"CountyFlowBackendDown", "CountyFlowWorkerDown", "CountyFlowApiErrorRateHigh", "CountyFlowInvariantViolation"} <= names
    error_rule = next(rule for rule in rules if rule["alert"] == "CountyFlowApiErrorRateHigh")
    assert ">= 100" in error_rule["expr"]
