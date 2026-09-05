"""Tests for prospective BRENTOIL profit-lock disposition."""

from __future__ import annotations

from hypervector.research.brentoil_profit_lock_decision import (
    evaluate_brentoil_profit_locks,
)

_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_POLICIES = (
    "a25_floor15_trail10",
    "a40_floor15_trail20",
    "a60_floor15_trail30",
)


def _preregistration() -> dict[str, object]:
    return {
        "live_identity": {
            "signal_strategy_id": _STRATEGY,
            "symbol": "xyz:BRENTOIL",
            "required_sides": ["long", "short"],
        },
        "prospective_boundary": {"capture_start_ms": 1_000},
        "hypothesis_formation_evidence": {
            "excluded_lifecycle_ids": ["xyz:BRENTOIL:excluded"]
        },
        "exit_policy_diagnostic": {"policy_ids": list(_POLICIES)},
    }


def _result(
    lifecycle_id: str, side: str, deltas: tuple[float, ...]
) -> dict[str, object]:
    return {
        "lifecycle_id": lifecycle_id,
        "strategy_id": _STRATEGY,
        "symbol": "xyz:BRENTOIL",
        "side": side,
        "status": "eligible",
        "completed_bars_expected": 10,
        "completed_bars_observed": 10,
        "policies": {
            policy: {
                "estimated_minus_actual_net_usd": delta,
                "status": "triggered",
            }
            for policy, delta in zip(_POLICIES, deltas, strict=True)
        },
    }


def _checkpoint(results: list[dict[str, object]]) -> dict[str, object]:
    trades = [
        {
            "lifecycle_id": row["lifecycle_id"],
            "entry": {"venue_timestamp_ms": 2_000},
        }
        for row in results
    ]
    return {
        "audit": {
            "profit_lock_challenger": {
                "all_time_live_mechanism": {"latest_results": results}
            },
            "trade_reflections": {"all_time_live": {"trades": trades}},
        }
    }


def test_decision_excludes_predeclared_lifecycle_and_requires_both_sides() -> None:
    """A positive short cannot select a policy without prospective long evidence."""
    results = [
        _result("xyz:BRENTOIL:excluded", "long", (5.0, 5.0, 5.0)),
        _result("xyz:BRENTOIL:short", "short", (2.0, 1.0, 0.0)),
    ]

    report = evaluate_brentoil_profit_locks(_checkpoint(results), _preregistration())

    assert report["eligible_lifecycle_ids"] == ["xyz:BRENTOIL:short"]
    assert report["side_coverage"] == {"long": 0, "short": 1}
    assert report["passed"] is False
    assert report["decision"] == "retain_v61_no_lock_collect_both_sides"


def test_policy_passes_only_with_positive_both_side_and_leave_largest_delta() -> None:
    """The V62 policy gate requires robust improvement beyond one lifecycle."""
    results = [
        _result("xyz:BRENTOIL:long", "long", (3.0, 3.0, 3.0)),
        _result("xyz:BRENTOIL:short", "short", (2.0, -1.0, 0.0)),
    ]

    report = evaluate_brentoil_profit_locks(_checkpoint(results), _preregistration())

    assert report["policies"]["a25_floor15_trail10"]["passed"] is True
    assert report["policies"]["a40_floor15_trail20"]["passed"] is False
    assert report["policies"]["a60_floor15_trail30"]["passed"] is False
    assert report["passed"] is True
    assert report["eligible_policy_ids"] == ["a25_floor15_trail10"]


def test_incomplete_candle_coverage_invalidates_lifecycle() -> None:
    """Missing completed bars cannot support a counterfactual lock decision."""
    result = _result("xyz:BRENTOIL:short", "short", (2.0, 1.0, 1.0))
    result["completed_bars_observed"] = 9

    report = evaluate_brentoil_profit_locks(_checkpoint([result]), _preregistration())

    assert report["eligible_lifecycle_ids"] == []
    assert report["excluded_incomplete_candle_lifecycle_ids"] == ["xyz:BRENTOIL:short"]
