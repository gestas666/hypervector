"""Independent-window checks for report-only opportunity capture."""

import pytest

from hypervector.research.cohort_forward_paths import DirectionalPath
from hypervector.research.cohort_opportunity_capture import (
    opportunity_hurdles,
    summarize_path_opportunities,
)
from hypervector.research.cohort_signal_candidates import SignalCandidate
from hypervector.research.cohort_signal_outcomes import (
    _HorizonEvidence,
    _horizon_summary,
    _provider_evidence,
    _provider_summary,
    _record_one_blocker,
)


def _path(timestamp_ms: int, close_bps: float, mfe_bps: float) -> DirectionalPath:
    return DirectionalPath(timestamp_ms, close_bps, mfe_bps, 4.0)


def test_horizon_summary_separates_overlapping_and_independent_opportunities() -> None:
    """One sustained move must not count as several independent missed trades."""
    evidence = _HorizonEvidence(
        outcomes=[
            _path(0, 20.0, 30.0),
            _path(60_000, 18.0, 28.0),
            _path(300_000, -5.0, 8.0),
        ]
    )

    summary = _horizon_summary(evidence, 5, opportunity_hurdles(13.0, 26.0))

    assert summary["resolved"] == 3
    assert summary["non_overlapping_resolved"] == 2
    assert summary["opportunity_capture"]["robust_mfe_count"] == 2
    independent = summary["independent_opportunity_capture"]
    assert independent["resolved"] == 2
    assert independent["robust_mfe_count"] == 1
    assert independent["cost_clearing_close_count"] == 1


def test_one_blocker_summary_preserves_long_and_short_outcomes() -> None:
    """Opposing sides must not be pooled into one misleading near-miss result."""
    evidence = _provider_evidence((60,))
    base = {
        "strategy_id": "strategy",
        "symbol": "HYPE",
        "reference_price": 50.0,
        "eligible": False,
        "blockers": ("awaiting_breakout",),
        "metrics": {},
    }
    long = SignalCandidate(decision_time_ms=0, side="long", **base)
    short = SignalCandidate(decision_time_ms=3_600_000, side="short", **base)
    _record_one_blocker(evidence, long, 60, "resolved", _path(0, 30.0, 40.0))
    _record_one_blocker(
        evidence,
        short,
        60,
        "resolved",
        _path(3_600_000, -20.0, 5.0),
    )

    summary = _provider_summary(evidence, opportunity_hurdles(13.0, 26.0))
    sides = summary["one_blocker_near_misses"]["by_blocker"]["awaiting_breakout"][
        "by_side"
    ]

    assert (
        sides["long"]["horizons"]["60"]["opportunity_capture"][
            "cost_clearing_close_count"
        ]
        == 1
    )
    assert (
        sides["short"]["horizons"]["60"]["opportunity_capture"][
            "cost_clearing_close_count"
        ]
        == 0
    )


def test_opportunity_distribution_exposes_outlier_driven_positive_mean() -> None:
    """Median and range must reveal when one winner dominates two losing paths."""
    outcomes = [
        _path(0, 8.15093936235689, 15.633768940912507),
        _path(1_800_000, 7.610248467937453, 11.215103005381977),
        _path(3_600_000, 57.100165430385985, 85.91707134852244),
    ]

    capture = summarize_path_opportunities(
        outcomes,
        opportunity_hurdles(13.0, 26.0),
    )

    assert capture["mean_close_after_estimated_friction_bps"] == pytest.approx(
        11.28711775356011
    )
    assert capture["median_close_after_estimated_friction_bps"] == pytest.approx(
        -4.84906063764311
    )
    assert capture["minimum_close_after_estimated_friction_bps"] == pytest.approx(
        -5.389751532062547
    )
    assert capture["maximum_close_after_estimated_friction_bps"] == pytest.approx(
        44.100165430385985
    )
    assert capture[
        "mean_excluding_largest_close_after_estimated_friction_bps"
    ] == pytest.approx(-5.119406084852828)
