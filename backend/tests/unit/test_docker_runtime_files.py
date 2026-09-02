import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_docker_runtime_declares_real_infrastructure_and_distinct_workers() -> None:
    compose_file = PROJECT_ROOT / "docker-compose.yml"
    backend_dockerfile = PROJECT_ROOT / "backend" / "Dockerfile"
    frontend_dockerfile = PROJECT_ROOT / "frontend" / "Dockerfile"
    frontend_nginx = PROJECT_ROOT / "frontend" / "nginx.conf"

    assert compose_file.is_file()
    assert backend_dockerfile.is_file()
    assert frontend_dockerfile.is_file()
    assert frontend_nginx.is_file()
    assert "try_files $uri $uri/ /index.html;" in frontend_nginx.read_text(encoding="utf-8")

    compose = compose_file.read_text(encoding="utf-8")
    assert compose.startswith("name: countyflow-ai")
    assert "mysql:" in compose
    assert "redis:" in compose
    assert "qdrant:" in compose
    assert "neo4j:" in compose
    assert "image: neo4j:5.26-community" in compose
    assert "NEO4J_AUTH:" in compose
    assert "/data/dbms/auth.ini" in compose
    assert "unset NEO4J_AUTH" in compose
    assert "/startup/docker-entrypoint.sh" in compose
    assert "GRAPH_MEMORY_BACKEND: neo4j" in compose
    assert "NEO4J_URI: bolt://neo4j:7687" in compose
    assert "countyflow_neo4j:/data" in compose
    assert "internal: true" in compose
    assert "countyflow_host_access" in compose
    assert "host_access:" in compose
    assert "condition: service_healthy" in compose
    assert "worker-1:" in compose
    assert "worker-2:" in compose
    assert "migration:" in compose
    assert "sqlite+pysqlite" not in compose
    assert "fakeredis" not in compose
    assert "RUNTIME_PROFILE: docker-dev" in compose
    assert "ENVIRONMENT_PROVIDER: docker-development" in compose
    assert "CAPACITY_PROVIDER: in-memory" in compose
    assert "ROUTING_PROVIDER: in-memory" in compose
    assert "DATABASE_BACKEND: mysql" in compose
    assert "REDIS_BACKEND: server" in compose
    assert "QDRANT_BACKEND: server" in compose
    assert "MEMORY_MUTATION_API_ENABLED: true" in compose
    assert "MEMORY_MUTATION_LOCK_TTL_MS: 10000" in compose
    assert "RUNTIME_OVERRIDE_API_ENABLED: true" in compose
    assert "RUNTIME_OVERRIDE_LOCK_TTL_MS: 8000" in compose
    assert "RUNTIME_CHECKPOINT_INTERRUPT_AFTER: environment" in compose
    assert "WORKER_CONSUMER_NAME: worker-1" in compose
    assert "WORKER_CONSUMER_NAME: worker-2" in compose


def test_docker_runtime_adds_observability_without_changing_checkpoint_redis() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services_block = compose.split("services:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    service_names = [
        line.strip().removesuffix(":")
        for line in services_block.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")
    ]

    assert service_names == [
        "mysql",
        "redis",
        "qdrant",
        "neo4j",
        "migration",
        "backend",
        "worker-1",
        "worker-2",
        "frontend",
        "prometheus",
        "grafana",
    ]
    redis_block = services_block.split("  redis:\n", 1)[1].split("\n  qdrant:\n", 1)[0]
    assert "image: redis:8.2.9-alpine" in redis_block
    assert '["redis-server", "--appendonly", "yes"]' in redis_block
    assert "redis-checkpoint" not in service_names
    assert "RUNTIME_CHECKPOINT_NAMESPACE: countyflow" in services_block


def test_backend_declares_official_redis_checkpointer_compatible_with_checkpoint_v4() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert "langgraph-checkpoint-redis>=0.5.2,<0.6" in dependencies


def test_workers_can_reach_external_providers_without_exposing_ports() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    worker_1 = compose.split("  worker-1:\n", 1)[1].split("\n  worker-2:\n", 1)[0]
    worker_2 = compose.split("  worker-2:\n", 1)[1].split("\n  frontend:\n", 1)[0]
    for worker in (worker_1, worker_2):
        assert "    networks:\n      - default\n      - host_access" in worker
        assert "    ports:" not in worker


def test_graph_memory_integration_entrypoint_is_executable_without_connecting() -> None:
    powershell_script = PROJECT_ROOT / "scripts" / "test-graph-memory.ps1"
    integration_script = PROJECT_ROOT / "scripts" / "graph_memory_integration.py"

    assert powershell_script.is_file()
    result = subprocess.run(
        [sys.executable, str(integration_script), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "20 warm Neo4j graph-memory queries" in result.stdout
    source = integration_script.read_text(encoding="utf-8")
    assert '("driver-li", "xinping-road", "national-102")' in source
    assert '"required_path"' in source


def test_shared_memory_integration_entrypoint_covers_real_visibility_protocol() -> None:
    powershell_script = PROJECT_ROOT / "scripts" / "test-shared-memory.ps1"
    integration_script = PROJECT_ROOT / "scripts" / "shared_memory_integration.py"

    assert powershell_script.is_file()
    result = subprocess.run(
        [sys.executable, str(integration_script), "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "real MySQL, Redis, Qdrant, and Neo4j" in result.stdout

    source = integration_script.read_text(encoding="utf-8")
    for evidence in (
        "qdrant_success_neo4j_failure",
        "neo4j_success_qdrant_failure",
        "staged_projection_invisible",
        "finalize_crash_reconciled",
        "redis_single_lock_winner",
        "mysql_single_v7_to_v8_winner",
        "one_mutation_two_attempts",
    ):
        assert evidence in source

    docker_test = (PROJECT_ROOT / "scripts" / "test-docker.ps1").read_text(encoding="utf-8")
    assert "test-shared-memory.ps1" in docker_test


def test_full_runtime_launcher_and_docker_test_entrypoints_are_relative() -> None:
    launcher = PROJECT_ROOT / "一键启动完整版.bat"
    start_script = PROJECT_ROOT / "scripts" / "start-full.ps1"
    test_script = PROJECT_ROOT / "scripts" / "test-docker.ps1"

    assert launcher.is_file()
    assert start_script.is_file()
    assert test_script.is_file()
    assert "%~dp0" in launcher.read_text(encoding="utf-8")
    for script in (start_script, test_script):
        text = script.read_text(encoding="utf-8")
        assert "$PSScriptRoot" in text
        assert "C:\\Users\\24090" not in text


def test_docker_test_script_filters_mysql_client_warning_lines() -> None:
    test_script = PROJECT_ROOT / "scripts" / "test-docker.ps1"
    text = test_script.read_text(encoding="utf-8")

    assert "function Get-MySqlScalar" in text
    assert '"-u{0}" -f $dockerEnv.MYSQL_USER' in text
    assert "docker_ws_e2e.py" in text
    assert "StatusCode -ne 202" in text
    assert "memory-rain-li" in text
    assert "REROUTED" in text
    assert "XPENDING countyflow:dispatch:tasks countyflow-workers" in text
    assert "[System.Text.Encoding]::UTF8.GetBytes($body)" in text


def test_docker_websocket_e2e_requires_eight_agent_graph_evidence() -> None:
    websocket_script = (PROJECT_ROOT / "scripts" / "docker_ws_e2e.py").read_text(encoding="utf-8")

    assert '"GRAPH_MEMORY_COMPLETED"' in websocket_script
    assert '"HAS_RISK_ON"' in websocket_script
    assert '"HIGH_RISK_WHEN"' in websocket_script
    assert '"ALTERNATIVE_TO"' in websocket_script
    assert "eight-agent events" in websocket_script


def test_checkpoint_integration_and_recovery_harnesses_cover_real_acceptance() -> None:
    checkpoint_script = PROJECT_ROOT / "scripts" / "checkpoint_integration.py"
    recovery_script = PROJECT_ROOT / "scripts" / "docker_checkpoint_recovery_e2e.py"
    powershell_script = PROJECT_ROOT / "scripts" / "test-checkpoint.ps1"

    assert checkpoint_script.is_file()
    assert recovery_script.is_file()
    assert powershell_script.is_file()
    checkpoint_source = checkpoint_script.read_text(encoding="utf-8")
    for evidence in ("write_latency_ms", "exact_read_latency_ms", "minimum", "average", "p95", "maximum", "payload_bytes", "20"):
        assert evidence in checkpoint_source
    recovery_source = recovery_script.read_text(encoding="utf-8")
    for evidence in (
        "THREAD_CHECKPOINTED",
        "canonical_checkpoint_id",
        "state_version",
        "worker-1",
        "worker-2",
        "xpending",
        "dispatch_count",
        "audit_count",
        "memory_mutation_count",
        "national-102",
        "memory-rain-li",
        "APPROVED",
        "REROUTE",
    ):
        assert evidence in recovery_source


def test_docker_runtime_exposes_read_only_runtime_thread_panel() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    frontend_dockerfile = (PROJECT_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

    assert "RUNTIME_THREAD_API_ENABLED: true" in compose
    assert "AUTHENTICATION_PROVIDER: ${AUTHENTICATION_PROVIDER:?AUTHENTICATION_PROVIDER is required}" in compose
    assert "RUNTIME_THREAD_AUTHORIZATION_PROVIDER" not in compose
    assert "VITE_RUNTIME_THREAD_STATE_ENABLED: true" in compose
    assert "ARG VITE_RUNTIME_THREAD_STATE_ENABLED=false" in frontend_dockerfile


def test_v2_d2_browser_harness_is_api_mode_and_restores_runtime_safely() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    package = (PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    config = PROJECT_ROOT / "frontend" / "playwright.config.ts"
    runner = PROJECT_ROOT / "scripts" / "test-browser-e2e.ps1"

    assert "RUNTIME_THREAD_AUTHORIZATION_PROVIDER" not in compose
    assert '"test:e2e"' in package
    assert config.is_file()
    assert "http://localhost:5173" in config.read_text(encoding="utf-8")
    assert runner.is_file()
    source = runner.read_text(encoding="utf-8")
    for evidence in (
        "worker-2",
        "E2E_ACCESS_TOKEN",
        "create_dev_token.py",
        "finally",
        "runtime-override-forbidden.spec.ts",
        "XPENDING countyflow:dispatch:tasks countyflow-workers",
    ):
        assert evidence in source


def test_observability_harness_covers_targets_provisioning_failures_and_overhead() -> None:
    runner = PROJECT_ROOT / "scripts" / "test-observability.ps1"
    integration = PROJECT_ROOT / "scripts" / "observability_integration.py"
    failures = PROJECT_ROOT / "scripts" / "observability_failure_e2e.py"
    alerts = PROJECT_ROOT / "scripts" / "observability_alert_e2e.py"
    overhead = PROJECT_ROOT / "scripts" / "observability_overhead.py"
    for path in (runner, integration, failures, alerts, overhead):
        assert path.is_file()

    integration_source = integration.read_text(encoding="utf-8")
    for evidence in ("backend", "worker-1", "worker-2", "countyflow-prometheus", "countyflow-v2-operations"):
        assert evidence in integration_source
    assert "real_dispatch_task_id" in integration_source
    assert "agent_execution_delta" in integration_source
    assert "graph_query_delta" in integration_source
    failure_source = failures.read_text(encoding="utf-8")
    for evidence in ("neo4j", "worker-1", "worker-2", "prometheus", "grafana", "finally"):
        assert evidence in failure_source
    alert_source = alerts.read_text(encoding="utf-8")
    for evidence in ("CountyFlowDependencyDown", '"pending"', '"firing"', '"resolved"', "finally"):
        assert evidence in alert_source
    assert alert_source.index("wait_for(None") < alert_source.index('compose("stop", "neo4j")')
    assert 'wait_for("firing", 240)' in alert_source
    overhead_source = overhead.read_text(encoding="utf-8")
    for evidence in ("observability_off", "observability_on", "api_p95_ms", "graph_p95_ms", "override_p95_ms", "worker_throughput", "qps", "error_rate"):
        assert evidence in overhead_source

    docker_test = (PROJECT_ROOT / "scripts" / "test-docker.ps1").read_text(encoding="utf-8")
    check_script = (PROJECT_ROOT / "scripts" / "check.ps1").read_text(encoding="utf-8")
    assert "test-observability.ps1" in docker_test
    assert "test-observability.ps1" in check_script
    assert "observability_alert_e2e.py" in runner.read_text(encoding="utf-8")


def test_observability_browser_specs_are_api_mode_and_cover_unavailable_states() -> None:
    live = (PROJECT_ROOT / "frontend" / "e2e" / "observability-live.spec.ts").read_text(encoding="utf-8")
    failures = (PROJECT_ROOT / "frontend" / "e2e" / "observability-failures.spec.ts").read_text(encoding="utf-8")
    assert "LIVE OBSERVABILITY" in live
    assert "VERIFIED ACCEPTANCE" in live
    assert 'getByText("DEMO DATA", { exact: true })).toHaveCount(0)' in live
    assert "Monitoring unavailable" in failures
    assert "Monitoring permission required" in failures


def test_current_browser_harnesses_and_dashboard_use_eleven_service_topology() -> None:
    for name in ("test-browser-e2e.ps1", "test-v2-f-browser.ps1"):
        source = (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert ".Count -ne 11" in source
        assert "eleven-service" in source.lower() or "eleven_service" in source.lower()
        assert "nine-service" not in source
    dashboard = (PROJECT_ROOT / "frontend" / "src" / "components" / "v2-capability-summary.tsx").read_text(
        encoding="utf-8"
    )
    assert 'label: "11 项服务"' in dashboard
    assert "Prometheus · Grafana" in dashboard
