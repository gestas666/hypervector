"""Exact decision-metric diagnostics for causal cohort outcomes."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_signal_metric_diagnostics import (
    MetricDiagnosticsAccumulator,
)


def test_numeric_metric_separates_positive_and_nonpositive_paths() -> None:
    """Exact numeric values remain paired with resolved directional outcomes."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 60_000, {"adx": 18.0}, 12.0)
    _observe_resolved(evidence, 120_000, {"adx": 14.0}, -8.0)

    report = evidence.as_payload()
    metric = report["metrics"]["adx"]
    assert report["coverage"] == {
        "complete": True,
        "evaluations_with_metrics": 2,
        "evaluations_without_metrics": 0,
        "metric_value_gaps": 0,
    }
    assert metric["kind"] == "numeric"
    assert metric["observations"] == 2
    assert metric["mean"] == 16.0
    horizon = metric["horizons"]["5"]
    assert horizon["resolved"] == 2
    assert horizon["non_overlapping_resolved"] == 1
    assert horizon["positive_directional_rate"] == 0.5
    assert horizon["positive_directional"] == {
        "count": 1,
        "mean_metric": 18.0,
        "mean_directional_return_bps": 12.0,
    }
    assert horizon["nonpositive_directional"] == {
        "count": 1,
        "mean_metric": 14.0,
        "mean_directional_return_bps": -8.0,
    }


def test_categorical_metric_reports_outcomes_by_exact_json_value() -> None:
    """Categorical states are not coerced into continuous measurements."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 60_000, {"squeeze_on": True}, 12.0)
    _observe_resolved(evidence, 120_000, {"squeeze_on": True}, 4.0)
    _observe_resolved(evidence, 360_000, {"squeeze_on": False}, -8.0)

    metric = evidence.as_payload()["metrics"]["squeeze_on"]
    assert metric["kind"] == "categorical"
    assert metric["categories"] == [
        {"value": False, "count": 1},
        {"value": True, "count": 2},
    ]
    assert metric["horizons"]["5"]["by_value"] == [
        {
            "value": False,
            "resolved": 1,
            "non_overlapping_resolved": 1,
            "positive_directional_rate": 0.0,
            "mean_directional_return_bps": -8.0,
        },
        {
            "value": True,
            "resolved": 2,
            "non_overlapping_resolved": 1,
            "positive_directional_rate": 1.0,
            "mean_directional_return_bps": 8.0,
        },
    ]
    assert metric["horizons"]["5"]["by_value_onset"] == [
        {
            "value": False,
            "resolved": 1,
            "non_overlapping_resolved": 1,
            "censored": 0,
            "missing_data": 0,
            "positive_directional_rate": 0.0,
            "mean_directional_return_bps": -8.0,
        },
        {
            "value": True,
            "resolved": 1,
            "non_overlapping_resolved": 1,
            "censored": 0,
            "missing_data": 0,
            "positive_directional_rate": 1.0,
            "mean_directional_return_bps": 12.0,
        },
    ]


def test_metric_horizons_reject_nonchronological_observations() -> None:
    """State onsets require strict provider-local decision ordering."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 120_000, {"squeeze_on": True}, 4.0)
    evidence.observe_evaluation({"squeeze_on": False})

    with pytest.raises(ValueError, match="strictly increasing"):
        evidence.observe_horizon(
            {"squeeze_on": False},
            horizon_minutes=5,
            decision_time_ms=60_000,
            status="resolved",
            directional_return_bps=-1.0,
        )


def test_absent_metric_is_a_technical_metric_coverage_gap() -> None:
    """A later empty metric map remains evidence but cannot look complete."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 60_000, {"adx": 18.0}, 12.0)
    evidence.observe_evaluation({})
    evidence.observe_horizon(
        {},
        horizon_minutes=5,
        decision_time_ms=360_000,
        status="censored",
        directional_return_bps=None,
    )

    report = evidence.as_payload()
    assert report["coverage"] == {
        "complete": False,
        "evaluations_with_metrics": 1,
        "evaluations_without_metrics": 1,
        "metric_value_gaps": 1,
    }
    metric = report["metrics"]["adx"]
    assert metric["missing_evaluations"] == 1
    assert metric["horizons"]["5"]["metric_missing"] == 1


def test_declared_warmup_unavailability_is_not_a_metric_coverage_gap() -> None:
    """Null metrics under a declared warmup are unavailable, not dropped telemetry."""
    evidence = MetricDiagnosticsAccumulator((5,))
    warmup = {
        "metric_availability": "warmup_unavailable",
        "side_hint": None,
        "close": None,
    }
    _observe_resolved(evidence, 60_000, warmup, -2.0)
    measured = {"metric_availability": "available", "side_hint": "long", "close": 140.0}
    _observe_resolved(evidence, 360_000, measured, 8.0)

    report = evidence.as_payload()

    assert report["coverage"]["complete"] is True
    assert report["coverage"]["metric_value_gaps"] == 0
    for name in ("side_hint", "close"):
        assert report["metrics"][name]["missing_evaluations"] == 0
        assert report["metrics"][name]["horizons"]["5"]["metric_missing"] == 0


def test_undeclared_null_metrics_remain_coverage_gaps() -> None:
    """Without the declaration, a null metric is a telemetry gap."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 60_000, {"side_hint": None, "close": None}, -2.0)
    _observe_resolved(evidence, 360_000, {"side_hint": "long", "close": 140.0}, 8.0)

    report = evidence.as_payload()

    assert report["coverage"]["complete"] is False
    assert report["coverage"]["metric_value_gaps"] == 2


def test_available_pressure_with_null_values_remains_missing() -> None:
    """An available book status cannot hide absent pressure measurements."""
    evidence = MetricDiagnosticsAccumulator((5,))
    measured = {
        "pressure_status": "available",
        "imbalance_10": 0.4,
        "pressure_age_seconds": 10.0,
    }
    _observe_resolved(evidence, 60_000, measured, 8.0)
    missing = {
        "pressure_status": "available",
        "imbalance_10": None,
        "pressure_age_seconds": None,
    }
    _observe_resolved(evidence, 360_000, missing, -2.0)

    report = evidence.as_payload()

    assert report["coverage"]["complete"] is False
    assert report["coverage"]["metric_value_gaps"] == 2


def test_inactive_stop_price_is_declared_unavailable_not_missing() -> None:
    """A stop exists only for eligible entries and is not missing on a hold."""
    evidence = MetricDiagnosticsAccumulator((5,))
    evidence.observe_evaluation(
        {"atr": 30.0, "stop_price": None},
        explicitly_unavailable=frozenset({"stop_price"}),
    )
    evidence.observe_horizon(
        {"atr": 30.0, "stop_price": None},
        horizon_minutes=5,
        decision_time_ms=60_000,
        status="resolved",
        directional_return_bps=-2.0,
        explicitly_unavailable=frozenset({"stop_price"}),
    )
    _observe_resolved(
        evidence,
        360_000,
        {"atr": 31.0, "stop_price": 946.5},
        8.0,
    )

    report = evidence.as_payload()

    assert report["coverage"]["complete"] is True
    assert report["coverage"]["metric_value_gaps"] == 0
    assert report["metrics"]["stop_price"]["missing_evaluations"] == 0
    assert report["metrics"]["stop_price"]["horizons"]["5"]["metric_missing"] == 0


def test_eligible_null_stop_price_remains_a_coverage_gap() -> None:
    """Callers must not hide an absent stop when an entry claims eligibility."""
    evidence = MetricDiagnosticsAccumulator((5,))
    _observe_resolved(evidence, 60_000, {"atr": 30.0, "stop_price": None}, -2.0)
    _observe_resolved(
        evidence,
        360_000,
        {"atr": 31.0, "stop_price": 946.5},
        8.0,
    )

    report = evidence.as_payload()

    assert report["coverage"]["complete"] is False
    assert report["coverage"]["metric_value_gaps"] == 1


def test_metric_type_drift_and_unsupported_values_are_rejected() -> None:
    """Audit evidence fails explicitly instead of coercing incompatible values."""
    evidence = MetricDiagnosticsAccumulator((5,))
    evidence.observe_evaluation({"adx": 18.0})

    with pytest.raises(ValueError, match="adx changed type"):
        evidence.observe_evaluation({"adx": "eighteen"})
    with pytest.raises(ValueError, match="unsupported value"):
        MetricDiagnosticsAccumulator((5,)).observe_evaluation({"bad": [1, 2]})


def _observe_resolved(
    evidence: MetricDiagnosticsAccumulator,
    decision_time_ms: int,
    metrics: dict[str, object],
    directional_return_bps: float,
) -> None:
    evidence.observe_evaluation(metrics)
    evidence.observe_horizon(
        metrics,
        horizon_minutes=5,
        decision_time_ms=decision_time_ms,
        status="resolved",
        directional_return_bps=directional_return_bps,
    )
