"""Tests for fixed-entry HYPE compression regime-loss exit evidence."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research import hype_compression_exit_challenger as challenger
from hypervector.research.hype_breakout_exit_models import (
    HypeExitReason,
    HypeExitReplayConfig,
    HypeExitTrade,
)


def test_persistent_opposition_and_adverse_close_exit_at_next_open() -> None:
    """Five opposed completed bars and a 20-bps loss trigger causally."""
    market = _opposed_market()
    control = _control_trade(market, exit_reason="maximum_hold")

    result = challenger.replay_fixed_lifecycle_regime_loss_exit(
        market,
        control,
        HypeExitReplayConfig(),
        loss_threshold_bps=20.0,
        persistence_decisions=5,
    )

    expected_raw = float(market["open"].iloc[6])
    expected_exit = expected_raw * (1.0 - 2.0 / 10_000.0)
    expected_gross = (expected_exit / control.entry_price - 1.0) * 10_000.0
    expected_fee = 4.5 * (1.0 + expected_exit / control.entry_price)
    assert result.policy_triggered is True
    assert result.candidate_applied is True
    assert result.trigger_decision_time_utc == market.index[6].isoformat()
    assert result.candidate_exit_time_utc == market.index[6].isoformat()
    assert result.candidate_exit_price == pytest.approx(expected_exit)
    assert result.candidate_net_return_bps == pytest.approx(
        expected_gross - expected_fee
    )
    assert result.actual_net_return_bps == control.net_return_bps


def test_protective_stop_at_candidate_open_retains_actual_exit() -> None:
    """A venue stop at the same bar wins over the report-only candidate."""
    market = _opposed_market()
    control = _control_trade(
        market,
        exit_reason="protective_stop",
        exit_position=6,
    )

    result = challenger.replay_fixed_lifecycle_regime_loss_exit(
        market,
        control,
        HypeExitReplayConfig(),
        loss_threshold_bps=20.0,
        persistence_decisions=5,
    )

    assert result.policy_triggered is True
    assert result.candidate_applied is False
    assert result.candidate_disposition == "actual_exit_precedes_or_coincides"
    assert result.candidate_exit_price == control.exit_price
    assert result.candidate_net_return_bps == control.net_return_bps


def test_candidate_settles_only_funding_before_its_exit() -> None:
    """The paired candidate does not inherit funding from the later control exit."""
    market = _opposed_market()
    market.loc[market.index[2], "funding_rate"] = 0.001
    market.loc[market.index[7], "funding_rate"] = 0.009
    control = _control_trade(market, exit_reason="maximum_hold")

    result = challenger.replay_fixed_lifecycle_regime_loss_exit(
        market,
        control,
        HypeExitReplayConfig(),
        loss_threshold_bps=20.0,
        persistence_decisions=5,
    )

    expected = -0.001 * float(market["open"].iloc[2]) / control.entry_price * 10_000
    assert result.candidate_funding_bps == pytest.approx(expected)
    assert result.candidate_funding_bps != control.funding_bps


def test_comparison_reports_paired_entries_without_execution_authority() -> None:
    """The report changes exits only and retains every control entry identity."""
    market = _opposed_market()
    control = _control_trade(market, exit_reason="maximum_hold")

    comparison = challenger.compare_fixed_regime_loss_exits(
        market,
        (control,),
        HypeExitReplayConfig(),
        loss_threshold_bps=20.0,
        persistence_decisions=5,
        fold_count=1,
    )

    assert comparison.report["execution_authority"] == "none"
    assert comparison.report["policy_id"] == "opp5_loss20"
    assert comparison.report["entry_lifecycles"] == 1
    assert comparison.report["candidate_applied_lifecycles"] == 1
    assert comparison.report["actual"]["net_return_bps"] == control.net_return_bps
    assert comparison.report["candidate_minus_actual_net_bps"] == pytest.approx(
        comparison.report["candidate"]["net_return_bps"] - control.net_return_bps
    )
    assert comparison.trade_rows["entry_time_utc"].tolist() == [control.entry_time_utc]


def _opposed_market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=9, freq="1min", tz="UTC")
    close = [100.0, 99.98, 99.96, 99.94, 99.92, 99.70, 99.65, 99.60, 99.55]
    return pd.DataFrame(
        {
            "open": [100.0, 100.0, 99.98, 99.96, 99.94, 99.92, 99.65, 99.60, 99.55],
            "high": [100.05] * 9,
            "low": [99.50] * 9,
            "close": close,
            "funding_rate": [0.0] * 9,
            "entry_side": [None] * 9,
            "state_1m": ["TREND_DOWN"] * 9,
            "state_5m": ["TREND_DOWN"] * 9,
            "context_15m": ["TREND_DOWN"] * 9,
            "structural_direction": ["short"] * 9,
        },
        index=index,
    )


def _control_trade(
    market: pd.DataFrame,
    *,
    exit_reason: HypeExitReason,
    exit_position: int = 8,
) -> HypeExitTrade:
    return HypeExitTrade(
        side="long",
        signal_time_utc=market.index[0].isoformat(),
        entry_time_utc=market.index[1].isoformat(),
        exit_time_utc=market.index[exit_position].isoformat(),
        entry_price=100.0,
        exit_price=99.55,
        stop_price=99.2,
        gross_return_bps=-45.0,
        fee_bps=9.0,
        funding_bps=0.0,
        net_return_bps=-54.0,
        hold_minutes=7,
        maximum_favorable_excursion_bps=5.0,
        maximum_adverse_excursion_bps=50.0,
        exit_reason=exit_reason,
    )
