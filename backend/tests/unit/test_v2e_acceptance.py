import pytest

from app.acceptance.v2e import (
    GraphAcceptanceCase,
    RoundEvidence,
    summarize_graph_acceptance,
    validate_round_evidence,
)


def test_round_evidence_requires_one_contiguous_fifteen_round_conversation():
    rounds = [
        RoundEvidence(
            round_number=number,
            task_id="task-one",
            thread_id="thread-one",
            checkpoint_id=f"checkpoint-{number}",
            state_version=number,
            current_node="capacity" if number == 13 else "routing",
            next_node="routing" if number == 13 else "dispatch",
        )
        for number in range(1, 16)
    ]

    summary = validate_round_evidence(rounds)

    assert summary.rounds == 15
    assert summary.task_ids == ("task-one",)
    assert summary.thread_ids == ("thread-one",)
    assert summary.passed is True


def test_round_evidence_rejects_context_switch_and_missing_round():
    rounds = [
        RoundEvidence(number, "task-one", "thread-one", f"cp-{number}", number, "routing", "dispatch")
        for number in range(1, 15)
    ]
    rounds[-1] = RoundEvidence(15, "task-two", "thread-one", "cp-15", 15, "routing", "dispatch")

    with pytest.raises(ValueError, match="contiguous rounds 1 through 15"):
        validate_round_evidence(rounds)


def test_graph_acceptance_requires_twenty_exact_real_recall_cases_and_p95_below_limit():
    cases = [
        GraphAcceptanceCase(
            query_id=f"graph-{number:02d}",
            expected_fact=("driver-li", "HAS_RISK_ON", "xinping-road"),
            actual_facts=(("driver-li", "HAS_RISK_ON", "xinping-road"),),
            expected_path=("driver-li", "xinping-road", "national-102"),
            actual_paths=(("driver-li", "xinping-road", "national-102"),),
            elapsed_ms=float(number),
        )
        for number in range(1, 21)
    ]

    summary = summarize_graph_acceptance(cases, warm_timings_ms=[float(number) for number in range(1, 51)])

    assert summary.queries == 20
    assert summary.fact_correct == 20
    assert summary.path_correct == 20
    assert summary.warm_queries == 50
    assert summary.p95_ms == 48.0
    assert summary.passed is True


def test_graph_acceptance_fails_when_any_expected_fact_is_absent():
    cases = [
        GraphAcceptanceCase(
            query_id=f"graph-{number:02d}",
            expected_fact=("driver-li", "HAS_RISK_ON", "xinping-road"),
            actual_facts=() if number == 20 else (("driver-li", "HAS_RISK_ON", "xinping-road"),),
            expected_path=None,
            actual_paths=(),
            elapsed_ms=1.0,
        )
        for number in range(1, 21)
    ]

    summary = summarize_graph_acceptance(cases, warm_timings_ms=[1.0] * 50)

    assert summary.fact_correct == 19
    assert summary.passed is False
