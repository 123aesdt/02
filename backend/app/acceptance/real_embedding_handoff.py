"""Strict V2-E real-embedding handoff validation and report finalization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EXPECTED_PROVIDER_HOST = "api.siliconflow.cn"
EXPECTED_MODEL = "Qwen/Qwen3-Embedding-4B"
EXPECTED_DIMENSION = 2560
EXPECTED_DATASET_SIZE = 50
EXPECTED_MEMORY_COUNT = 10
MINIMUM_TOP1_CORRECT = 46


class RealEmbeddingConfigurationError(ValueError):
    """Raised when the local handoff is not configured for the locked real flow."""


class RealEmbeddingResultError(ValueError):
    """Raised when a benchmark result cannot serve as V2-E evidence."""


@dataclass(frozen=True)
class RealEmbeddingConfiguration:
    base_url: str
    api_key: str = field(repr=False)
    model: str = EXPECTED_MODEL
    dimension: int = EXPECTED_DIMENSION
    provider_host: str = EXPECTED_PROVIDER_HOST


def validate_real_embedding_configuration(
    environment: Mapping[str, str], qdrant_url: str
) -> RealEmbeddingConfiguration:
    names = (
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSION",
    )
    values = {name: environment.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RealEmbeddingConfigurationError(
            f"Missing required embedding configuration: {', '.join(missing)}"
        )

    parsed = urlparse(values["EMBEDDING_BASE_URL"])
    if parsed.scheme != "https" or parsed.hostname != EXPECTED_PROVIDER_HOST:
        raise RealEmbeddingConfigurationError(
            "Real benchmark requires the HTTPS SiliconFlow embedding endpoint"
        )
    if values["EMBEDDING_MODEL"] != EXPECTED_MODEL:
        raise RealEmbeddingConfigurationError(
            f"Real benchmark requires model {EXPECTED_MODEL}"
        )
    try:
        dimension = int(values["EMBEDDING_DIMENSION"])
    except ValueError as error:
        raise RealEmbeddingConfigurationError(
            f"Real benchmark requires dimension {EXPECTED_DIMENSION}"
        ) from error
    if dimension != EXPECTED_DIMENSION:
        raise RealEmbeddingConfigurationError(
            f"Real benchmark requires dimension {EXPECTED_DIMENSION}"
        )
    if qdrant_url.strip() == ":memory:" or not urlparse(qdrant_url).hostname:
        raise RealEmbeddingConfigurationError(
            "Real benchmark requires a real Qdrant server URL"
        )

    return RealEmbeddingConfiguration(
        base_url=values["EMBEDDING_BASE_URL"],
        api_key=values["EMBEDDING_API_KEY"],
        model=values["EMBEDDING_MODEL"],
        dimension=dimension,
        provider_host=parsed.hostname,
    )


def build_v2e_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "as_of",
        "provider_base_host",
        "model",
        "dimension",
        "formal_real_embedding",
        "dataset_size",
        "memory_count",
        "top1_correct",
        "top1_accuracy",
        "top3_hits",
        "top3_hit_rate",
        "failed_queries",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise RealEmbeddingResultError(
            f"Benchmark result is missing required fields: {', '.join(missing)}"
        )
    if payload["formal_real_embedding"] is not True:
        raise RealEmbeddingResultError("Fake or development embedding evidence is forbidden")
    if payload["provider_base_host"] != EXPECTED_PROVIDER_HOST:
        raise RealEmbeddingResultError("Benchmark result is not from the locked provider host")
    if payload["model"] != EXPECTED_MODEL:
        raise RealEmbeddingResultError("Benchmark result is not from the locked model")
    if int(payload["dimension"]) != EXPECTED_DIMENSION:
        raise RealEmbeddingResultError("Benchmark result has the wrong vector dimension")
    if int(payload["dataset_size"]) != EXPECTED_DATASET_SIZE:
        raise RealEmbeddingResultError("Benchmark result must contain exactly 50 queries")
    if int(payload["memory_count"]) != EXPECTED_MEMORY_COUNT:
        raise RealEmbeddingResultError("Benchmark result must contain exactly 10 memories")

    top1_correct = int(payload["top1_correct"])
    top3_correct = int(payload["top3_hits"])
    return {
        "provider_host": str(payload["provider_base_host"]),
        "model": str(payload["model"]),
        "dimension": int(payload["dimension"]),
        "dataset_size": int(payload["dataset_size"]),
        "memory_count": int(payload["memory_count"]),
        "top1_correct": top1_correct,
        "top1_accuracy": float(payload["top1_accuracy"]),
        "top3_correct": top3_correct,
        "top3_hit_rate": float(payload["top3_hit_rate"]),
        "failed_queries": list(payload["failed_queries"]),
        "timestamp": str(payload["as_of"]),
        "passed": top1_correct >= MINIMUM_TOP1_CORRECT,
    }


def update_final_acceptance_text(report: str, result: Mapping[str, Any]) -> str:
    passed = result.get("passed") is True
    top1 = int(result["top1_correct"])
    total = int(result["dataset_size"])
    top3 = int(result["top3_correct"])
    top1_rate = float(result["top1_accuracy"])
    top3_rate = float(result["top3_hit_rate"])
    status = "PASS" if passed else "FAIL"

    report = re.sub(
        r"^Overall status: \*\*.*?\*\*$",
        "Overall status: **COMPLETE**" if passed else "Overall status: **BLOCKED by failed Vector Embedding regression**",
        report,
        flags=re.MULTILINE,
    )
    evidence_summary = (
        "All previously verified V2-E acceptance evidence remains unchanged. The fresh local real-embedding regression passed the locked threshold."
        if passed
        else (
            "All previously verified V2-E acceptance evidence remains unchanged, but the fresh local real-embedding regression "
            "did not meet the locked threshold."
        )
    )
    report = re.sub(
        r"^All locally controllable V2-E acceptance items passed\..*$",
        evidence_summary,
        report,
        flags=re.MULTILINE,
    )
    report = re.sub(
        r"^\| Vector Top-1 \|.*$",
        f"| Vector Top-1 | >=92% | {top1}/{total} ({top1_rate:.2%}) | {status} |",
        report,
        flags=re.MULTILINE,
    )
    report = re.sub(
        r"^\| Vector Top-3 \|.*$",
        f"| Vector Top-3 | regression | {top3}/{total} ({top3_rate:.2%}) | {status} |",
        report,
        flags=re.MULTILINE,
    )
    verdict = (
        "Final verdict: **V2-E COMPLETE** — the fresh local real-embedding regression passed, and all previously verified V2-E evidence remains valid."
        if passed
        else "Final verdict: **NOT VERIFIED** — the fresh local real-embedding regression did not meet Top-1 >=92%."
    )
    return re.sub(r"^Final verdict:.*$", verdict, report, flags=re.MULTILINE)


def write_v2e_reports(
    result: Mapping[str, Any], final_report_path: Path, vector_report_path: Path
) -> None:
    current = final_report_path.read_text(encoding="utf-8")
    final_report_path.write_text(
        update_final_acceptance_text(current, result), encoding="utf-8"
    )
    status = "VERIFIED" if result.get("passed") is True else "FAILED"
    vector_report = f"""# V2-E Real Vector Memory Acceptance

Status: **{status}**

This is the fresh local-only real embedding regression result. It reuses the existing 50-query / 10-memory benchmark and Qdrant cosine Top-K flow.

| Field | Result |
|---|---:|
| Provider host | {result['provider_host']} |
| Model | {result['model']} |
| Dimension | {result['dimension']} |
| Dataset | {result['dataset_size']} queries / {result['memory_count']} memories |
| Top-1 | {result['top1_correct']}/{result['dataset_size']} ({float(result['top1_accuracy']):.2%}) |
| Top-3 | {result['top3_correct']}/{result['dataset_size']} ({float(result['top3_hit_rate']):.2%}) |
| Threshold | >=46/50 Top-1 |
| Timestamp | {result['timestamp']} |
"""
    vector_report_path.parent.mkdir(parents=True, exist_ok=True)
    vector_report_path.write_text(vector_report, encoding="utf-8")


def write_result(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
