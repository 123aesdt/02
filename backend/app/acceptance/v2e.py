from collections.abc import Sequence
from dataclasses import dataclass

from app.acceptance.metrics import nearest_rank_percentile

GraphFact = tuple[str, str, str]
GraphEntityPath = tuple[str, ...]


@dataclass(frozen=True)
class RoundEvidence:
    round_number: int
    task_id: str
    thread_id: str
    checkpoint_id: str
    state_version: int
    current_node: str
    next_node: str | None


@dataclass(frozen=True)
class RoundEvidenceSummary:
    rounds: int
    task_ids: tuple[str, ...]
    thread_ids: tuple[str, ...]
    passed: bool


def validate_round_evidence(rounds: Sequence[RoundEvidence]) -> RoundEvidenceSummary:
    expected_rounds = list(range(1, 16))
    actual_rounds = [item.round_number for item in rounds]
    task_ids = tuple(sorted({item.task_id for item in rounds}))
    thread_ids = tuple(sorted({item.thread_id for item in rounds}))
    complete_fields = all(
        item.task_id
        and item.thread_id
        and item.checkpoint_id
        and item.current_node
        and item.state_version >= 0
        for item in rounds
    )
    if actual_rounds != expected_rounds or len(task_ids) != 1 or len(thread_ids) != 1 or not complete_fields:
        raise ValueError("Evidence must contain contiguous rounds 1 through 15 in one task and thread context.")
    return RoundEvidenceSummary(len(rounds), task_ids, thread_ids, True)


@dataclass(frozen=True)
class GraphAcceptanceCase:
    query_id: str
    expected_fact: GraphFact
    actual_facts: tuple[GraphFact, ...]
    expected_path: GraphEntityPath | None
    actual_paths: tuple[GraphEntityPath, ...]
    elapsed_ms: float

    @property
    def fact_passed(self) -> bool:
        return self.expected_fact in self.actual_facts

    @property
    def path_passed(self) -> bool:
        return self.expected_path is None or self.expected_path in self.actual_paths


@dataclass(frozen=True)
class GraphAcceptanceSummary:
    queries: int
    fact_correct: int
    path_correct: int
    warm_queries: int
    p95_ms: float
    passed: bool


def summarize_graph_acceptance(
    cases: Sequence[GraphAcceptanceCase],
    *,
    warm_timings_ms: Sequence[float],
) -> GraphAcceptanceSummary:
    if len(cases) < 20:
        raise ValueError("Graph acceptance requires at least 20 structured queries.")
    if len(warm_timings_ms) < 50:
        raise ValueError("Graph acceptance requires at least 50 warm queries.")
    fact_correct = sum(item.fact_passed for item in cases)
    path_correct = sum(item.path_passed for item in cases)
    p95_ms = nearest_rank_percentile(warm_timings_ms, 95)
    passed = fact_correct == len(cases) and path_correct == len(cases) and p95_ms < 150.0
    return GraphAcceptanceSummary(
        queries=len(cases),
        fact_correct=fact_correct,
        path_correct=path_correct,
        warm_queries=len(warm_timings_ms),
        p95_ms=p95_ms,
        passed=passed,
    )
