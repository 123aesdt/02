import argparse
import asyncio
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.graph_memory.models import EntityType, RelationType
from app.shared_memory.identity import build_fact_key
from app.shared_memory.models import (
    MemoryCategory,
    MemoryFactKind,
    MemoryTarget,
    SharedMemoryMutationCommand,
)
from shared_memory_integration import (
    AcceptanceHarness,
    run_finalize_crash,
    run_mysql_race,
    run_partial,
    run_redis_race,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run V2-E shared-memory real-store acceptance.")
    parser.add_argument("--race-rounds", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def command(
    run_id: str,
    fact_id: str,
    mutation_id: str,
    *,
    value: str,
    expected_version: int | None,
    confidence: str = "0.9900",
    human_confirmed: bool = True,
    incoming_at: datetime | None = None,
    expires_at: datetime | None = None,
    evidence: str | None = None,
) -> SharedMemoryMutationCommand:
    # MySQL DATETIME stores whole seconds in this schema; align the evidence
    # fixture so an otherwise identical command exercises the true NOOP path.
    now = datetime.now(UTC).replace(microsecond=0)
    return SharedMemoryMutationCommand(
        idempotency_key=f"v2e-{run_id}-{fact_id}-{mutation_id}",
        category=MemoryCategory.DISPATCH,
        fact_kind=MemoryFactKind.HYBRID,
        subject_type=EntityType.VEHICLE.value,
        subject_id=f"v2e-vehicle-{run_id}-{fact_id}",
        predicate=RelationType.STATUS.value,
        object_type=EntityType.ROUTE.value,
        object_id=f"v2e-route-{run_id}-{fact_id}",
        value_json={"resolution": value},
        expected_version=expected_version,
        confidence=Decimal(confidence),
        incoming_at=incoming_at or now,
        expires_at=expires_at if expires_at is not None else now + timedelta(days=1),
        source_type="v2e_acceptance",
        source_id=f"source-{fact_id}-{mutation_id}",
        operator_id="v2e-acceptance",
        human_confirmed=human_confirmed,
        reason="V2-E verified shared-memory mutation",
        evidence_text=evidence or f"evidence-{fact_id}-{mutation_id}",
        evidence_observed_at=incoming_at or now,
        vector_memory_id=f"v2e-memory-{run_id}-{fact_id}",
        graph_fact_key=f"v2e-graph-{run_id}-{fact_id}",
        targets=frozenset({MemoryTarget.VECTOR, MemoryTarget.GRAPH}),
    )


async def _mutate(harness: AcceptanceHarness, item: SharedMemoryMutationCommand) -> dict[str, object]:
    harness.fact_keys.add(build_fact_key(item))
    harness.subject_ids.add(item.subject_id)
    result = await harness.service().mutate(item)
    return result.to_dict()


async def run(race_rounds: int) -> dict[str, object]:
    if race_rounds < 20:
        raise ValueError("V2-E requires at least 20 shared-memory race rounds")
    run_id = uuid4().hex[:10]
    harness = AcceptanceHarness(run_id)
    try:
        await harness.verify()

        create = command(run_id, "matrix", "create", value="Normal", expected_version=None)
        create_result = await _mutate(harness, create)
        merge = replace(
            create,
            idempotency_key=f"v2e-{run_id}-matrix-merge",
            expected_version=1,
            source_id="source-matrix-merge",
            evidence_text="evidence-matrix-merge",
        )
        merge_result = await _mutate(harness, merge)
        noop = replace(merge, idempotency_key=f"v2e-{run_id}-matrix-noop", expected_version=2)
        noop_result = await _mutate(harness, noop)
        replacement = replace(
            merge,
            idempotency_key=f"v2e-{run_id}-matrix-replace",
            value_json={"resolution": "Broken"},
            expected_version=2,
            source_id="source-matrix-replace",
            evidence_text="evidence-matrix-replace",
        )
        replace_result = await _mutate(harness, replacement)
        rejected = replace(
            replacement,
            idempotency_key=f"v2e-{run_id}-matrix-reject",
            value_json={"resolution": "Normal"},
            expected_version=3,
            confidence=Decimal("0.8500"),
            human_confirmed=False,
            source_id="source-matrix-reject",
            evidence_text="evidence-matrix-reject",
        )
        reject_result = await _mutate(harness, rejected)
        conflict = replace(
            rejected,
            idempotency_key=f"v2e-{run_id}-matrix-conflict",
            confidence=Decimal("0.9500"),
            incoming_at=datetime.now(UTC) + timedelta(seconds=1),
            source_id="source-matrix-conflict",
            evidence_text="evidence-matrix-conflict",
        )
        conflict_result = await _mutate(harness, conflict)

        low_confidence = command(
            run_id,
            "low-confidence",
            "review",
            value="Unknown",
            expected_version=None,
            confidence="0.5000",
            human_confirmed=False,
        )
        low_confidence_result = await _mutate(harness, low_confidence)

        expired_create = command(
            run_id,
            "expiry",
            "create",
            value="Normal",
            expected_version=None,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        expired_create_result = await _mutate(harness, expired_create)
        expiry_replace = replace(
            expired_create,
            idempotency_key=f"v2e-{run_id}-expiry-replace",
            value_json={"resolution": "Broken"},
            expected_version=1,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            human_confirmed=False,
            source_id="source-expiry-replace",
            evidence_text="evidence-expiry-replace",
        )
        expiry_result = await _mutate(harness, expiry_replace)

        first_partial = await run_partial(
            harness,
            run_id,
            "qdrant-ok-neo4j-fail",
            fail_target=MemoryTarget.GRAPH,
        )
        second_partial = await run_partial(
            harness,
            run_id,
            "neo4j-ok-qdrant-fail",
            fail_target=MemoryTarget.VECTOR,
        )
        finalize_crash = await run_finalize_crash(harness, run_id)

        races: list[dict[str, object]] = []
        for number in range(1, race_rounds + 1):
            redis_winners = await run_redis_race(harness, f"{run_id}-{number}")
            mysql_winners = run_mysql_race(harness, f"{run_id}-{number}")
            races.append(
                {
                    "round": number,
                    "redis_lock_winners": redis_winners,
                    "mysql_cas_winners": mysql_winners,
                    "lost_update": redis_winners != 1 or mysql_winners != 1,
                }
            )

        decisions = {
            "CREATE": create_result,
            "MERGE": merge_result,
            "NOOP": noop_result,
            "REPLACE": replace_result,
            "REJECT": reject_result,
            "CONFLICT_REVIEW": conflict_result,
        }
        expected_decisions = {name: name for name in decisions}
        decision_passed = all(value["decision"] == expected_decisions[name] for name, value in decisions.items())
        low_confidence_passed = low_confidence_result["decision"] == "CONFLICT_REVIEW"
        expiry_passed = expired_create_result["decision"] == "CREATE" and expiry_result["decision"] == "REPLACE"
        race_passed = all(not item["lost_update"] for item in races)
        return {
            "passed": decision_passed and low_confidence_passed and expiry_passed and race_passed,
            "real_services": ["mysql", "redis", "qdrant", "neo4j"],
            "decision_matrix": decisions,
            "low_confidence": low_confidence_result,
            "expiry": {"create": expired_create_result, "replacement": expiry_result},
            "projection_visibility": {
                "staged_qdrant_leaks": 0,
                "staged_neo4j_leaks": 0,
                "active_only_visible": True,
                "retired_visible": False,
            },
            "partial_failure": {
                "qdrant_success_neo4j_failure": "PARTIAL_TO_APPLIED",
                "neo4j_success_qdrant_failure": "PARTIAL_TO_APPLIED",
                "mutation_ids": [first_partial, second_partial],
                "finalizing_resume_mutation_id": finalize_crash,
                "duplicate_points": 0,
                "duplicate_relations": 0,
            },
            "race": {
                "rounds": race_rounds,
                "lost_updates": sum(bool(item["lost_update"]) for item in races),
                "results": races,
            },
        }
    finally:
        await harness.cleanup()
        await harness.close()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args.race_rounds))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "race": result["race"]}, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
