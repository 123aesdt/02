from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "summarize_security_performance.py"


def _module():
    spec = importlib.util.spec_from_file_location("countyflow_security_performance_summary", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_security_performance_summary_has_explicit_safe_profiles(tmp_path: Path) -> None:
    module = _module()
    stats = tmp_path / "security-on_stats.csv"
    stats.write_text(
        "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,"
        "Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,"
        "50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
        ",Aggregated,12000,0,80,90,1,250,100,250.5,0,80,90,100,110,140,180,210,230,245,249,250\n",
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "configuration": {"users": 50, "duration_seconds_per_formal_run": 60},
                "summary": {
                    "average_qps": 317.999,
                    "maximum_p95_ms": 240.0,
                    "maximum_error_rate_percent": 0.0,
                    "passed": True,
                },
            }
        ),
        encoding="utf-8",
    )

    result = module.summarize(stats, baseline)

    assert result["security_on"]["profile"] == {
        "authentication": "development_jwt",
        "authorization": "bearer",
        "role": "DISPATCHER",
        "rate_limiting": "enabled",
        "principal_strategy": "unique_per_virtual_user",
        "users": 50,
        "duration_seconds": 60,
        "spawn_rate_per_second": 25,
    }
    assert result["security_on"]["qps"] == 250.5
    assert result["security_on"]["p95_ms"] == 180.0
    assert result["security_on"]["unexpected_error_rate_percent"] == 0.0
    assert result["security_off_baseline"]["evidence_kind"] == "historical_verified_pre_v2_g2"
    assert result["security_off_baseline"]["security_was_disabled_for_current_run"] is False
    assert result["gates"] == {"qps_gte_200": True, "p95_lt_300_ms": True, "unexpected_error_rate_lt_0_1_percent": True}
    assert result["passed"] is True
    serialized = json.dumps(result)
    assert "Authorization" not in serialized
    assert "DEVELOPMENT_JWT_SECRET" not in serialized


def test_security_performance_runner_keeps_security_enabled_and_writes_v2_g2_evidence() -> None:
    runner = (PROJECT_ROOT / "scripts" / "test-security-performance.ps1").read_text(encoding="utf-8")
    for required in (
        "loadtests\\locustfile.py",
        "DEVELOPMENT_JWT_SECRET",
        "RUNTIME_PROFILE",
        "docker-dev",
        "LOCUST_TASK_ID",
        "summarize_security_performance.py",
        "security-on_stats.csv",
        "v2-g2-security-performance.json",
    ):
        assert required in runner
    assert "AUTHENTICATION_PROVIDER=disabled" not in runner
    assert "AUTHENTICATION_PROVIDER = 'disabled'" not in runner
    assert "Write-Host $env:DEVELOPMENT_JWT_SECRET" not in runner
