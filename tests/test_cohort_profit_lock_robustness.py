"""Tests for normalized profit-lock robustness diagnostics."""

from importlib import import_module

import pytest


def test_robustness_exposes_favorable_outlier_dependence() -> None:
    """A positive mean must not hide a negative leave-largest result."""
    module = import_module("hypervector.research.cohort_profit_lock_robustness")
    results = (
        _result("one", "profile-a", 100.0, "triggered"),
        _result("two", "profile-a", -10.0, "triggered"),
        _result("three", "profile-b", -10.0, "triggered"),
        _result("withheld", "profile-b", 1_000.0, "withheld_missing_bars"),
    )

    report = module.build_profit_lock_robustness_by_policy(results, ("lock",))

    lock = report["lock"]
    assert lock["lifecycles"] == 4
    assert lock["eligible_lifecycles"] == 3
    assert lock["withheld_lifecycles"] == 1
    assert lock["triggered_lifecycles"] == 3
    assert lock["distinct_source_runs"] == 3
    assert lock["distinct_source_profiles"] == 2
    delta = lock["all_eligible_delta_net_return_bps"]
    assert delta == {
        "count": 3,
        "positive_count": 1,
        "negative_count": 2,
        "zero_count": 0,
        "positive_fraction": pytest.approx(1.0 / 3.0),
        "mean": pytest.approx(80.0 / 3.0),
        "median": -10.0,
        "minimum": -10.0,
        "maximum": 100.0,
        "mean_excluding_most_favorable": -10.0,
        "mean_excluding_most_adverse": 45.0,
    }
    assert lock["triggered_delta_net_return_bps"] == delta


def _result(
    run_id: str,
    profile: str,
    delta_bps: float,
    status: str,
) -> dict[str, object]:
    notional = 100.0
    return {
        "source_run_id": run_id,
        "source_profile_fingerprint": profile,
        "entry_notional_usd": notional,
        "strategy_id": "strategy",
        "symbol": "SOL",
        "policies": {
            "lock": {
                "status": status,
                "actual_net_pnl_usd": 0.0,
                "estimated_net_pnl_usd": delta_bps / 10_000.0 * notional,
            }
        },
    }
