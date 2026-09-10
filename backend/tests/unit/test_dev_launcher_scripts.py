import os
import shutil
import subprocess
import sys
from pathlib import Path

import jwt

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HELPER = PROJECT_ROOT / "scripts" / "create_dev_token.py"
FULL_RUNTIME_BUILDER = PROJECT_ROOT / "scripts" / "build-full-runtime-images.ps1"


def run_helper(*arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("DEVELOPMENT_JWT_SECRET", "RUNTIME_PROFILE", "AUTH_ISSUER", "AUTH_AUDIENCE"):
        env.pop(key, None)
    env.update(environment or {})
    return subprocess.run(
        [sys.executable, str(HELPER), *arguments],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dev_token_helper_requires_ignored_secret_and_refuses_production() -> None:
    assert HELPER.is_file()
    missing = run_helper("--role", "DISPATCHER")
    assert missing.returncode != 0
    assert "DEVELOPMENT_JWT_SECRET is not configured" in missing.stderr

    secret = "test-only-signing-material-32-chars"
    production = run_helper(
        "--role",
        "ADMIN",
        environment={"DEVELOPMENT_JWT_SECRET": secret, "RUNTIME_PROFILE": "production"},
    )
    assert production.returncode != 0
    assert "forbidden in production" in production.stderr
    assert secret not in production.stdout + production.stderr


def test_dev_token_helper_emits_a_short_lived_role_limited_signed_jwt() -> None:
    secret = "test-only-signing-material-32-chars"
    result = run_helper(
        "--role",
        "DISPATCHER",
        "--ttl-seconds",
        "60",
        environment={
            "DEVELOPMENT_JWT_SECRET": secret,
            "RUNTIME_PROFILE": "docker-dev",
            "AUTH_ISSUER": "countyflow-dev",
            "AUTH_AUDIENCE": "countyflow-api",
        },
    )
    assert result.returncode == 0, result.stderr
    token = result.stdout.strip()
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="countyflow-dev",
        audience="countyflow-api",
    )
    assert claims["roles"] == ["DISPATCHER"]
    assert claims["sub"] == "dev-dispatcher"
    assert 1 <= claims["exp"] - claims["iat"] <= 60
    assert secret not in result.stdout + result.stderr


def test_dev_token_powershell_entrypoint_is_relative_and_secret_safe() -> None:
    script = PROJECT_ROOT / "scripts" / "create-dev-token.ps1"
    assert script.is_file()
    source = script.read_text(encoding="utf-8")
    assert "$PSScriptRoot" in source
    assert "create_dev_token.py" in source
    assert "DEVELOPMENT_JWT_SECRET" in source
    assert "Write-Host $env:DEVELOPMENT_JWT_SECRET" not in source
    assert "RUNTIME_PROFILE" in source
    assert "production" in source


def test_security_runner_and_docker_security_contract_are_wired() -> None:
    runner = PROJECT_ROOT / "scripts" / "test-security.ps1"
    integration = PROJECT_ROOT / "scripts" / "security_integration.py"
    assert runner.is_file()
    assert integration.is_file()
    source = runner.read_text(encoding="utf-8")
    assert "security_integration.py" in source
    assert "security-auth.spec.ts" in source
    assert "DEVELOPMENT_JWT_SECRET" in source
    assert "E2E_API_BASE_URL" in source
    assert "$PSScriptRoot" in source
    assert "test_endpoint_permissions.py" in source
    assert "test_authorization.py" not in source
    integration_source = integration.read_text(encoding="utf-8")
    for role in ("DISPATCHER", "SUPERVISOR", "OPERATOR", "AUDITOR", "ADMIN"):
        assert role in integration_source
    for path in (
        "/api/v1/auth/me",
        "/api/v1/observability/summary",
        "/api/v1/security/audit",
        "/api/v1/runtime/threads/",
        "/api/v1/ws-tickets",
    ):
        assert path in integration_source
    assert "429" in integration_source
    assert "4403" in integration_source
    assert "4408" in integration_source
    assert "print(token" not in integration_source

    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services = compose.split("services:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    names = [line.strip().removesuffix(":") for line in services.splitlines() if line.startswith("  ") and not line.startswith("    ") and line.endswith(":")]
    assert len(names) == 11
    assert "AUTHENTICATION_PROVIDER: ${AUTHENTICATION_PROVIDER:?AUTHENTICATION_PROVIDER is required}" in compose
    assert "DEVELOPMENT_JWT_SECRET: ${DEVELOPMENT_JWT_SECRET:?DEVELOPMENT_JWT_SECRET is required}" in compose
    assert "NEO4J_PASSWORD: ${NEO4J_PASSWORD:?NEO4J_PASSWORD is required}" in compose
    assert "NEO4J_PASSWORD: ${MYSQL_PASSWORD" not in compose
    assert 'GF_AUTH_ANONYMOUS_ENABLED: "false"' in compose
    assert "ADMIN" not in services.split("  migration:\n", 1)[1].split("\n  grafana:\n", 1)[0]


def test_full_launcher_generates_independent_ignored_dev_security_settings_without_auto_admin() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")
    for key in (
        "AUTHENTICATION_PROVIDER=development_jwt",
        "DEVELOPMENT_JWT_SECRET=",
        "AUTH_ISSUER=countyflow-dev",
        "AUTH_AUDIENCE=countyflow-api",
        "NEO4J_PASSWORD=",
    ):
        assert key in source
    assert "create-dev-token.ps1 -Role ADMIN" not in source
    assert "开发认证" in source
    assert "PrepareOnly" in source


def test_full_launcher_uses_chinese_user_facing_copy() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")
    for text in ("正在构建已验证镜像", "等待后端、前端和监控服务", "所有服务已就绪", "开发认证"):
        assert text in source
    for text in ("Building verified images", "Monitoring services ready", "DEV AUTH"):
        assert text not in source


def test_full_launcher_starts_docker_desktop_and_waits_without_leaking_native_errors() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")

    assert "function Test-DockerReady" in source
    assert "Docker Desktop.exe" in source
    assert "Programs\\DockerDesktop\\Docker Desktop.exe" in source
    assert "Start-Process -FilePath $dockerDesktop" in source
    assert "Docker Desktop 未运行，正在自动启动" in source
    assert "正在等待 Docker 引擎就绪" in source
    assert "Docker Desktop 启动超时" in source


def test_full_launcher_prefetches_build_images_before_buildkit() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")

    for image in (
        "python:3.12-slim",
        "node:22-alpine",
        "nginx:1.27-alpine",
        "qdrant/qdrant:v1.13.2",
        "mysql:8.4",
        "redis:8.2.9-alpine",
        "neo4j:5.26-community",
        "prom/prometheus:v3.5.0",
        "grafana/grafana:12.1.0",
    ):
        assert image in source
    assert "function Initialize-BuildImages" in source
    assert "正在准备 Docker 基础镜像" in source
    assert "基础镜像拉取失败" in source
    assert source.index("Initialize-BuildImages $dockerCommand") < source.index("& $builder -ProjectRoot")


def test_local_dev_launcher_uses_chinese_user_facing_copy() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")
    for text in ("正在启动后端", "后端已就绪", "正在启动前端", "本地开发模式"):
        assert text in source
    for text in ("Starting Backend", "Backend ready", "Starting Frontend", "NOT STARTED"):
        assert text not in source


def test_windows_batch_launchers_are_codepage_independent_ascii_wrappers() -> None:
    for filename in ("一键启动.bat", "一键启动完整版.bat"):
        source_bytes = (PROJECT_ROOT / filename).read_bytes()
        source = source_bytes.decode("ascii")

        assert all(byte < 128 for byte in source_bytes), filename
        assert "chcp" not in source.lower(), filename
        assert "title CountyFlow AI" in source, filename
        assert "pause >nul" in source, filename
        assert "\n    pause\n" not in source.replace("\r\n", "\n"), filename


def test_verified_full_runtime_builder_stages_and_hashes_without_docker() -> None:
    pwsh = shutil.which("pwsh")
    assert pwsh is not None
    assert FULL_RUNTIME_BUILDER.is_file()
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-File",
            str(FULL_RUNTIME_BUILDER),
            "-ProjectRoot",
            str(PROJECT_ROOT),
            "-ValidateOnly",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "已验证暂存 Docker 构建上下文" in result.stdout


def test_verified_full_runtime_builder_supports_windows_powershell() -> None:
    windows_powershell = shutil.which("powershell.exe")
    assert windows_powershell is not None
    assert FULL_RUNTIME_BUILDER.is_file()
    result = subprocess.run(
        [
            windows_powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(FULL_RUNTIME_BUILDER),
            "-ProjectRoot",
            str(PROJECT_ROOT),
            "-ValidateOnly",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "已验证暂存 Docker 构建上下文" in result.stdout


def test_full_launcher_uses_verified_images_and_disables_compose_build() -> None:
    source = (PROJECT_ROOT / "scripts" / "start-full.ps1").read_text(encoding="utf-8")
    assert "build-full-runtime-images.ps1" in source
    assert "up -d --no-build" in source
    assert "up -d --build" not in source


def test_verified_full_runtime_builder_forces_clean_build_layers() -> None:
    source = FULL_RUNTIME_BUILDER.read_text(encoding="utf-8")
    assert source.count("'--no-cache'") == 3


def test_verified_full_runtime_builder_materializes_onedrive_file_bytes() -> None:
    source = FULL_RUNTIME_BUILDER.read_text(encoding="utf-8")
    assert "[IO.File]::ReadAllBytes" in source
    assert "[IO.File]::WriteAllBytes" in source
    assert "Copy-Item" not in source


def test_docker_websocket_e2e_requests_ticket_and_never_uses_bearer_in_ws_url() -> None:
    source = (PROJECT_ROOT / "scripts" / "docker_ws_e2e.py").read_text(encoding="utf-8")
    assert '"/api/v1/ws-tickets"' in source
    assert '"Authorization"' in source
    assert "?ticket=" in source
    assert "access_token=" not in source
    assert "E2E_ACCESS_TOKEN" in source


def test_checkpoint_recovery_e2e_uses_bearer_without_cli_token() -> None:
    runner = (PROJECT_ROOT / "scripts" / "docker_checkpoint_recovery_e2e.py").read_text(encoding="utf-8")
    launcher = (PROJECT_ROOT / "scripts" / "test-checkpoint.ps1").read_text(encoding="utf-8")

    assert "E2E_ACCESS_TOKEN" in runner
    assert '"Authorization"' in runner
    assert "--access-token" not in runner
    assert "create_dev_token.py" in launcher
    assert "$env:E2E_ACCESS_TOKEN" in launcher
    assert "Write-Host $token" not in launcher
    assert "Write-Output $token" not in launcher


def test_observability_acceptance_uses_bearer_and_scoped_ws_ticket() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "test-observability.ps1").read_text(encoding="utf-8")
    runners = {
        name: (PROJECT_ROOT / "scripts" / name).read_text(encoding="utf-8")
        for name in (
            "observability_integration.py",
            "observability_failure_e2e.py",
            "observability_overhead.py",
        )
    }

    assert "create_dev_token.py" in launcher
    assert "--role SUPERVISOR" in launcher
    assert "$env:E2E_ACCESS_TOKEN" in launcher
    for name, source in runners.items():
        assert "E2E_ACCESS_TOKEN" in source, name
        assert "Authorization" in source, name
    assert '"/api/v1/ws-tickets"' in runners["observability_overhead.py"]
    assert "?ticket=" in runners["observability_overhead.py"]
    assert "access_token=" not in runners["observability_overhead.py"]


def test_browser_e2e_uses_signed_supervisor_without_legacy_auth_toggles() -> None:
    source = (PROJECT_ROOT / "scripts" / "test-browser-e2e.ps1").read_text(encoding="utf-8")
    assert "E2E_ACCESS_TOKEN" in source
    assert "create_dev_token.py" in source
    assert "--role SUPERVISOR" in source
    assert "$env:NEO4J_PASSWORD = $dockerEnv.NEO4J_PASSWORD" in source
    assert "runtime-override-forbidden.spec.ts" in source
    assert "RUNTIME_THREAD_AUTHORIZATION_PROVIDER=disabled" not in source
    assert "RUNTIME_THREAD_AUTHORIZATION_PROVIDER=trusted" not in source
    assert "$dockerEnv.MYSQL_PASSWORD" not in source.split("$env:NEO4J_PASSWORD", 1)[1].splitlines()[0]


def test_real_graph_verification_never_falls_back_to_mysql_password() -> None:
    scripts = (
        "scripts/test-shared-memory.ps1",
        "scripts/test-graph-memory.ps1",
        "scripts/shared_memory_integration.py",
        "scripts/resume_memory_mutation.py",
        "scripts/simulate_conversation.py",
        "scripts/v2e_restart_acceptance.py",
    )
    forbidden = (
        "$env:NEO4J_PASSWORD = $env:MYSQL_PASSWORD",
        'os.environ.get("NEO4J_PASSWORD") or os.environ.get("MYSQL_PASSWORD", "")',
        'os.environ.get("NEO4J_PASSWORD") or required("MYSQL_PASSWORD")',
    )

    for relative_path in scripts:
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "NEO4J_PASSWORD" in source
        assert all(value not in source for value in forbidden), relative_path


def test_backend_runtime_image_does_not_retain_build_only_pyproject() -> None:
    source = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    assert "rm -f pyproject.toml" in source


def test_neo4j_password_recovery_is_offline_secret_safe_and_non_destructive() -> None:
    script = PROJECT_ROOT / "scripts" / "recover-neo4j-password.ps1"
    helper = PROJECT_ROOT / "scripts" / "neo4j-offline-recovery.sh"
    assert script.is_file()
    assert helper.is_file()
    source = script.read_text(encoding="utf-8")
    helper_source = helper.read_text(encoding="utf-8")
    assert "$PSScriptRoot" in source
    assert ".docker.env" in source
    assert "network create --internal" in source
    assert "--network $recoveryNetwork" in source
    assert "--publish" not in source
    assert "countyflow-ai_countyflow_neo4j" in source and ':/data"' in source
    assert "NEO4J_AUTH=none" in source
    assert "CF_RECOVERY_PASSWORD" in source
    assert "neo4j-offline-recovery.sh" in source
    assert ":/recovery.sh:ro" in source
    assert "--detach" in source
    assert "exec $recoveryContainer /bin/bash /recovery.sh" in source
    assert "ALTER USER neo4j SET PASSWORD" in helper_source
    assert "/startup/docker-entrypoint.sh neo4j" not in helper_source
    assert "docker compose --env-file" in source
    assert "Write-Host $neo4jPassword" not in source
    assert "Write-Output $neo4jPassword" not in source
    assert "down -v" not in source
    assert "volume rm" not in source


def test_neo4j_offline_recovery_helper_uses_unix_line_endings() -> None:
    helper = PROJECT_ROOT / "scripts" / "neo4j-offline-recovery.sh"

    assert b"\r\n" not in helper.read_bytes()
