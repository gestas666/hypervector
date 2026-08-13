"""Risk-normalized late profit-lock research tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_risk_normalized_profit_lock import (
    build_open_risk_normalized_profit_lock_challenger,
    build_risk_normalized_profit_lock_mechanism,
    risk_normalized_policy,
    trend_runner_policy,
)
from hypervector.research.cohort_trade_reflection_index import Candle


@pytest.mark.parametrize(
    ("side", "stop_price"),
    (("long", 99.2), ("short", 100.8)),
)
def test_policy_scales_from_the_original_adverse_stop(
    side: str,
    stop_price: float,
) -> None:
    """Two-R activation and one-R protection must use entry risk, not a fixed bps."""
    policy = risk_normalized_policy(
        side,
        {"price": 100.0},
        {"trigger_price": stop_price},
    )

    assert policy.policy_id == "r2_floor1_trail1"
    assert policy.activation_bps == pytest.approx(160.0)
    assert policy.floor_bps == pytest.approx(80.0)
    assert policy.trailing_giveback_bps == pytest.approx(80.0)


def test_policy_rejects_a_stop_on_the_profitable_side() -> None:
    """Malformed stop provenance must fail instead of becoming negative risk."""
    with pytest.raises(ValueError, match="adverse side"):
        risk_normalized_policy(
            "long",
            {"price": 100.0},
            {"trigger_price": 100.8},
        )


def test_trend_runner_waits_for_five_r_before_trailing_two_r() -> None:
    """The late policy must preserve ordinary continuation before a large trend."""
    policy = trend_runner_policy(
        "long",
        {"price": 100.0},
        {"trigger_price": 99.2},
    )

    assert policy.policy_id == "r5_floor2_trail2"
    assert policy.activation_bps == pytest.approx(400.0)
    assert policy.floor_bps == pytest.approx(160.0)
    assert policy.trailing_giveback_bps == pytest.approx(160.0)


def test_open_challenger_arms_late_and_tracks_one_r_from_the_peak() -> None:
    """The late lock must preserve continuation while ratcheting after a large move."""
    report = build_open_risk_normalized_profit_lock_challenger(
        {
            60_000: Candle(60_000, 100.0, 101.7, 99.9, 101.6),
            120_000: Candle(120_000, 102.0, 110.0, 101.8, 109.0),
        },
        "long",
        {"price": 100.0, "size": 1.0, "venue_timestamp_ms": 10_000},
        {"trigger_price": 99.2},
        {
            "mark_price": 109.0,
            "fees_usd": 0.045,
            "funding_usd": 0.0,
            "active_lifecycle_marked_net_pnl_usd": 8.955,
        },
        240_000,
    )

    policy = report["policies"]["r2_floor1_trail1"]
    assert report["contract"]["execution_authority"] == "none"
    assert report["risk_multiple_contract"] == {
        "activation_r": 2.0,
        "floor_r": 1.0,
        "peak_giveback_r": 1.0,
    }
    assert policy["status"] == "armed_not_triggered"
    assert policy["active_stop_price"] == pytest.approx(109.12)


def test_open_challenger_withholds_when_protective_stop_is_missing() -> None:
    """Legacy open evidence cannot manufacture an original risk distance."""
    report = build_open_risk_normalized_profit_lock_challenger(
        {},
        "long",
        {"price": 100.0, "size": 1.0, "venue_timestamp_ms": 10_000},
        None,
        {
            "mark_price": 100.2,
            "fees_usd": 0.04,
            "funding_usd": 0.0,
            "active_lifecycle_marked_net_pnl_usd": 0.16,
        },
        60_000,
    )

    assert report["status"] == "withheld_missing_protective_stop"
    assert all(
        row["status"] == "withheld_missing_protective_stop"
        for row in report["policies"].values()
    )


def test_mechanism_is_report_only_with_no_implicit_performance_gate() -> None:
    """An empty evidence set must still disclose the exact non-authoritative contract."""
    report = build_risk_normalized_profit_lock_mechanism([], {}, [])

    assert report["mode"] == "cohort_risk_normalized_profit_lock_mechanism_v1"
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
        "automatic_promotion": False,
        "performance_gate": False,
        "portfolio_pnl_claimed": False,
    }
    assert report["summary_by_policy"]["r2_floor1_trail1"]["lifecycles"] == 0
    assert report["summary_by_policy"]["r5_floor2_trail2"]["lifecycles"] == 0
