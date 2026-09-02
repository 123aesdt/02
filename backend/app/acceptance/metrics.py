import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean


def nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        raise ValueError("Percentile requires at least one value.")
    if not 1 <= percentile <= 100:
        raise ValueError("Percentile must be between 1 and 100.")
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    return ordered[rank - 1]


@dataclass(frozen=True)
class RecoveryRun:
    run: int
    recovery_seconds: float
    dispatch_count: int
    audit_count: int
    pending: int
    message_lost: bool

    @property
    def passed(self) -> bool:
        return (
            self.recovery_seconds <= 5.0
            and self.dispatch_count == 1
            and self.audit_count == 1
            and self.pending == 0
            and not self.message_lost
        )


@dataclass(frozen=True)
class RecoverySummary:
    minimum_seconds: float
    average_seconds: float
    p95_seconds: float
    maximum_seconds: float
    failed_runs: list[int]

    @property
    def passed(self) -> bool:
        return not self.failed_runs


def summarize_recovery(runs: Sequence[RecoveryRun]) -> RecoverySummary:
    if not runs:
        raise ValueError("Recovery summary requires at least one run.")
    seconds = [run.recovery_seconds for run in runs]
    return RecoverySummary(
        minimum_seconds=min(seconds),
        average_seconds=fmean(seconds),
        p95_seconds=nearest_rank_percentile(seconds, 95),
        maximum_seconds=max(seconds),
        failed_runs=[run.run for run in runs if not run.passed],
    )
