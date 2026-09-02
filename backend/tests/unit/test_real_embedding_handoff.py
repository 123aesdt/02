import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from app.acceptance.real_embedding_handoff import (
    RealEmbeddingConfigurationError,
    build_v2e_result,
    update_final_acceptance_text,
    validate_real_embedding_configuration,
)

PROJECT_ROOT = Path(__file__).parents[3]
RUNNER = PROJECT_ROOT / "scripts" / "run_memory_benchmark.py"
POWERSHELL_ENTRYPOINT = PROJECT_ROOT / "scripts" / "run-real-embedding-benchmark.ps1"
FINAL_REPORT = PROJECT_ROOT / "docs" / "verification" / "v2-e" / "v2-e-final-acceptance.md"


def real_environment() -> dict[str, str]:
    return {
        "EMBEDDING_BASE_URL": "https://api.siliconflow.cn/v1",
        "EMBEDDING_API_KEY": "unit-test-secret-that-must-never-appear",
        "EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-4B",
        "EMBEDDING_DIMENSION": "2560",
    }


def real_payload() -> dict[str, object]:
    return {
        "as_of": "2026-08-27T12:00:00+00:00",
        "provider": "openai-compatible-real",
        "provider_base_host": "api.siliconflow.cn",
        "model": "Qwen/Qwen3-Embedding-4B",
        "dimension": 2560,
        "formal_real_embedding": True,
        "qdrant_url_kind": "server",
        "dataset_size": 50,
        "memory_count": 10,
        "top1_correct": 49,
        "top1_accuracy": 0.98,
        "top3_hits": 50,
        "top3_hit_rate": 1.0,
        "failed_queries": [{"query_id": "query-017"}],
    }


def test_strict_configuration_accepts_only_the_locked_real_provider():
    configuration = validate_real_embedding_configuration(real_environment(), "http://localhost:6333")

    assert configuration.provider_host == "api.siliconflow.cn"
    assert configuration.model == "Qwen/Qwen3-Embedding-4B"
    assert configuration.dimension == 2560


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"EMBEDDING_API_KEY": ""}, "Missing required embedding configuration"),
        ({"EMBEDDING_BASE_URL": "http://localhost:9999/v1"}, "SiliconFlow"),
        ({"EMBEDDING_MODEL": "fake/dev"}, "Qwen/Qwen3-Embedding-4B"),
        ({"EMBEDDING_DIMENSION": "128"}, "2560"),
    ],
)
def test_strict_configuration_rejects_missing_fake_or_dev_configuration_without_leaking_secret(change, message):
    environment = real_environment()
    environment.update(change)

    with pytest.raises(RealEmbeddingConfigurationError) as error:
        validate_real_embedding_configuration(environment, "http://localhost:6333")

    rendered = str(error.value)
    assert message in rendered
    assert real_environment()["EMBEDDING_API_KEY"] not in rendered
    assert "Authorization" not in rendered


def test_strict_configuration_rejects_in_memory_qdrant():
    with pytest.raises(RealEmbeddingConfigurationError, match="real Qdrant server"):
        validate_real_embedding_configuration(real_environment(), ":memory:")


def test_v2e_result_schema_is_machine_readable_and_secret_free():
    result = build_v2e_result(real_payload())

    assert result == {
        "provider_host": "api.siliconflow.cn",
        "model": "Qwen/Qwen3-Embedding-4B",
        "dimension": 2560,
        "dataset_size": 50,
        "memory_count": 10,
        "top1_correct": 49,
        "top1_accuracy": 0.98,
        "top3_correct": 50,
        "top3_hit_rate": 1.0,
        "failed_queries": [{"query_id": "query-017"}],
        "timestamp": "2026-08-27T12:00:00+00:00",
        "passed": True,
    }
    assert "key" not in json.dumps(result).lower()


def test_result_import_updates_only_the_missing_vector_evidence():
    report = (
        "# V2-E Final Acceptance\n\n"
        "Overall status: **BLOCKED only by required external Vector Embedding regression**\n\n"
        "All locally controllable V2-E acceptance items passed. The host security policy rejected the explicitly requested credentialed call "
        "carrying fixed benchmark text to `api.siliconflow.cn`; therefore the current-run Vector Top-1/Top-3 cells remain NOT VERIFIED, and V2-E "
        "cannot be declared COMPLETE.\n\n"
        "| Vector Top-1 | >=92% | outbound run denied | NOT VERIFIED |\n"
        "| Vector Top-3 | regression | outbound run denied | NOT VERIFIED |\n\n"
        "Final verdict: **NOT VERIFIED** until the current real benchmark runs.\n"
    )

    updated = update_final_acceptance_text(report, build_v2e_result(real_payload()))

    assert "Overall status: **COMPLETE**" in updated
    assert "| Vector Top-1 | >=92% | 49/50 (98.00%) | PASS |" in updated
    assert "| Vector Top-3 | regression | 50/50 (100.00%) | PASS |" in updated
    assert "Final verdict: **V2-E COMPLETE**" in updated
    assert "current-run Vector Top-1/Top-3 cells remain NOT VERIFIED" not in updated


def test_result_below_threshold_is_recorded_but_never_completes_v2e():
    payload = real_payload()
    payload.update({"top1_correct": 45, "top1_accuracy": 0.9})
    result = build_v2e_result(payload)
    report = """# V2-E Final Acceptance

Overall status: **BLOCKED only by required external Vector Embedding regression**

| Vector Top-1 | >=92% | outbound run denied | NOT VERIFIED |
| Vector Top-3 | regression | outbound run denied | NOT VERIFIED |

Final verdict: **NOT VERIFIED** until the current real benchmark runs.
"""

    updated = update_final_acceptance_text(report, result)

    assert result["passed"] is False
    assert "Overall status: **COMPLETE**" not in updated
    assert "| Vector Top-1 | >=92% | 45/50 (90.00%) | FAIL |" in updated
    assert "Final verdict: **NOT VERIFIED**" in updated


def test_current_complete_final_report_remains_verified_with_a_fresh_result():
    current = FINAL_REPORT.read_text(encoding="utf-8")

    updated = update_final_acceptance_text(current, build_v2e_result(real_payload()))

    assert "Overall status: **COMPLETE**" in updated
    assert "| Vector Memory Top-1 | >=92% | 49/50 (98.00%) | VERIFIED |" in updated
    assert "Final verdict: **V2-E COMPLETE**" in updated


def test_existing_runner_missing_real_config_exits_nonzero_without_network_or_secret_output():
    environment = os.environ.copy()
    for name in ("EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL", "EMBEDDING_DIMENSION"):
        environment.pop(name, None)
    with TemporaryDirectory(dir=PROJECT_ROOT) as temporary_directory:
        output = Path(temporary_directory) / "must-not-exist.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--require-real",
                "--output",
                str(output),
            ],
            cwd=PROJECT_ROOT,
            env={**environment, "PYTHONPATH": str(PROJECT_ROOT / "backend")},
            capture_output=True,
            text=True,
            check=False,
        )
        output_exists = output.exists()

    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "Missing required embedding configuration" in combined
    assert "Traceback" not in combined
    assert "Authorization" not in combined
    assert not output_exists


def test_powershell_entrypoint_reuses_existing_runner_and_never_accepts_key_as_an_argument():
    script = POWERSHELL_ENTRYPOINT.read_text(encoding="utf-8")

    assert "scripts\\run_memory_benchmark.py" in script
    assert "--require-real" in script
    assert "docs\\verification\\v2-e\\raw\\v2-e-real-embedding-regression.json" in script
    assert "EMBEDDING_API_KEY: CONFIGURED" in script
    assert "api-key" not in script.lower()
    assert ":memory:" not in script
