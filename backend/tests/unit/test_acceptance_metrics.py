import pytest

from app.acceptance.metrics import RecoveryRun, nearest_rank_percentile, summarize_recovery


def test_nearest_rank_percentile_uses_observed_value_without_interpolation():
    values = [810.0, 820.0, 830.0, 840.0, 850.0, 860.0, 870.0, 880.0, 890.0, 900.0]

    assert nearest_rank_percentile(values, 95) == 900.0


def test_recovery_summary_reports_distribution_and_all_invariant_failures():
    runs = [
        RecoveryRun(1, 3.1, 1, 1, 0, False),
        RecoveryRun(2, 3.2, 1, 1, 0, False),
        RecoveryRun(3, 3.3, 2, 1, 0, False),
        RecoveryRun(4, 3.4, 1, 1, 1, False),
        RecoveryRun(5, 5.1, 1, 1, 0, True),
    ]

    summary = summarize_recovery(runs)

    assert summary.minimum_seconds == 3.1
    assert summary.average_seconds == pytest.approx(3.62)
    assert summary.p95_seconds == 5.1
    assert summary.maximum_seconds == 5.1
    assert summary.failed_runs == [3, 4, 5]
    assert summary.passed is False
