"""Shared-capital replay tests for the frozen crypto participation sleeve."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.crypto_bull_participation_models import (
    CryptoBullParticipationConfig,
)
from hypervector.research.crypto_bull_participation_replay import (
    evaluate_crypto_bull_portfolio,
)


def test_replay_shifts_entry_and_honors_stop_rearm_and_profit_lock() -> None:
    """Entries use the next open and stop exits cannot rearm inside one state."""
    config = _config()
    minutes = _minute_frame()
    decisions = _decisions(minutes.index)
    report = evaluate_crypto_bull_portfolio(
        {"BTC": minutes},
        {"BTC": decisions},
        {"BTC": _funding(minutes.index)},
        config,
    )

    assert len(report.trades) == 2
    first, second = report.trades
    assert first.entry_time_utc == "2026-01-01T01:00:00+00:00"
    assert first.exit_time_utc == "2026-01-01T01:30:00+00:00"
    assert first.exit_reason == "protective_stop"
    assert first.exit_price == pytest.approx(97.0)
    assert second.entry_time_utc == "2026-01-01T03:00:00+00:00"
    assert second.exit_reason == "profit_lock"
    assert second.exit_price == pytest.approx(102.72)
    assert report.maximum_concurrent_positions == 1


def test_primary_signal_exit_executes_at_next_boundary_with_costs_and_funding() -> None:
    """Trend deterioration is primary; funding and both taker legs reconcile."""
    config = _config(entry_fee_bps=4.0, exit_fee_bps=4.0)
    minutes = _flat_minutes(periods=181)
    decisions = pd.DataFrame(
        {
            "entry_onset": [True, False, False],
            "entry_eligible": [True, True, False],
            "exit_signal": [False, False, True],
            "breadth": [1, 1, 0],
            "completed_hour_high": [100.0, 101.0, 100.0],
        },
        index=pd.date_range("2026-01-01T01:00:00Z", periods=3, freq="h"),
    )
    funding = _funding(minutes.index)
    funding.loc[pd.Timestamp("2026-01-01T02:00:00Z")] = 0.001

    report = evaluate_crypto_bull_portfolio(
        {"BTC": minutes}, {"BTC": decisions}, {"BTC": funding}, config
    )

    trade = report.trades[0]
    assert trade.exit_time_utc == "2026-01-01T03:00:00+00:00"
    assert trade.exit_reason == "trend_deterioration"
    assert trade.funding_cashflow_usd == pytest.approx(-0.2)
    assert trade.fees_usd == pytest.approx(0.16)
    assert trade.net_pnl_usd == pytest.approx(-0.36)
    assert report.final_equity_usd == pytest.approx(999.64)


def test_gap_through_isolated_liquidation_is_explicitly_reported() -> None:
    """A discontinuous gap cannot be mislabeled as an ordinary stop fill."""
    config = _config()
    minutes = _flat_minutes(periods=121)
    gap_time = pd.Timestamp("2026-01-01T02:00:00Z")
    minutes.loc[gap_time, ["open", "high", "low", "close"]] = [40.0, 41.0, 39.0, 40.0]
    decisions = pd.DataFrame(
        {
            "entry_onset": [True, False],
            "entry_eligible": [True, True],
            "exit_signal": [False, False],
            "breadth": [1, 1],
            "completed_hour_high": [100.0, 100.0],
        },
        index=pd.date_range("2026-01-01T01:00:00Z", periods=2, freq="h"),
    )

    report = evaluate_crypto_bull_portfolio(
        {"BTC": minutes},
        {"BTC": decisions},
        {"BTC": _funding(minutes.index)},
        config,
    )

    trade = report.trades[0]
    assert trade.exit_time_utc == "2026-01-01T02:00:00+00:00"
    assert trade.exit_reason == "liquidation"
    assert trade.exit_price == pytest.approx(40.0)


def _config(
    *, entry_fee_bps: float = 0.0, exit_fee_bps: float = 0.0
) -> CryptoBullParticipationConfig:
    return CryptoBullParticipationConfig(
        symbols=("BTC",),
        fast_ema_hours=2,
        slow_ema_hours=3,
        minimum_ema_hours=3,
        entry_breadth=1,
        exit_breadth=1,
        initial_equity_usd=1000.0,
        margin_fraction_per_position=0.1,
        leverage=2.0,
        maximum_positions=1,
        maximum_total_margin_fraction=0.1,
        protective_stop_bps=300.0,
        profit_lock_activation_bps=600.0,
        profit_lock_floor_bps=100.0,
        profit_lock_giveback_bps=400.0,
        maximum_hold_minutes=43_200,
        entry_fee_bps=entry_fee_bps,
        exit_fee_bps=exit_fee_bps,
        adverse_slippage_bps_per_side=0.0,
    )


def _minute_frame() -> pd.DataFrame:
    frame = _flat_minutes(periods=301)
    frame.loc[pd.Timestamp("2026-01-01T01:30:00Z"), "low"] = 96.5
    third_hour = frame.loc["2026-01-01T03:01:00Z":"2026-01-01T03:59:00Z"]
    frame.loc[third_hour.index, ["open", "high", "low", "close"]] = 106.0
    fourth_hour = frame.loc["2026-01-01T04:00:00Z":"2026-01-01T04:59:00Z"]
    frame.loc[fourth_hour.index, ["open", "high", "low", "close"]] = 106.0
    frame.loc[pd.Timestamp("2026-01-01T03:10:00Z"), "high"] = 107.0
    frame.loc[pd.Timestamp("2026-01-01T04:30:00Z"), "low"] = 102.0
    return frame


def _flat_minutes(*, periods: int) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=periods, freq="min", tz="UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0},
        index=index,
    )


def _decisions(index: pd.DatetimeIndex) -> pd.DataFrame:
    del index
    return pd.DataFrame(
        {
            "entry_onset": [True, False, True, False, False],
            "entry_eligible": [True, False, True, True, True],
            "exit_signal": [False, True, False, False, False],
            "breadth": [1, 0, 1, 1, 1],
            "completed_hour_high": [101.0, 100.0, 101.0, 107.0, 107.0],
        },
        index=pd.date_range("2026-01-01T01:00:00Z", periods=5, freq="h"),
    )


def _funding(index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(0.0, index=index, name="funding_rate")
