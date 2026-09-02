from __future__ import annotations

import inspect
from pathlib import Path

from app.runtime_overrides.query_service import RuntimeOverrideQueryService
from app.runtime_overrides.service import RuntimeOverrideService
from app.runtime_threads.service import ThreadStateService

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_services_require_request_principal_instead_of_global_authorizer() -> None:
    assert "authorizer" not in inspect.signature(ThreadStateService).parameters
    assert "principal" in inspect.signature(ThreadStateService.get_current_by_thread).parameters
    assert "authorizer" not in inspect.signature(RuntimeOverrideQueryService).parameters
    assert "principal" in inspect.signature(RuntimeOverrideQueryService.get_intervention_context).parameters
    assert "authorizer" not in inspect.signature(RuntimeOverrideService).parameters
    assert inspect.signature(RuntimeOverrideService.apply).parameters["principal"].default is inspect.Parameter.empty


def test_runtime_configuration_has_no_trusted_or_disabled_authorizer_switch() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    config = (PROJECT_ROOT / "backend" / "app" / "core" / "config.py").read_text(encoding="utf-8")
    for forbidden in (
        "RUNTIME_THREAD_AUTHORIZATION_PROVIDER",
        "MEMORY_MUTATION_AUTHORIZATION_PROVIDER",
        "OBSERVABILITY_AUTHORIZATION_PROVIDER",
        "TrustedRuntimeThreadAuthorizer",
        "TrustedObservabilityAuthorizer",
    ):
        assert forbidden not in compose
        assert forbidden.lower() not in config.lower()
