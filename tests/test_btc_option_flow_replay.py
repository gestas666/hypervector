"""Tests for the frozen live-shaped BTC option-flow economic replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_option_flow_replay import (
    evaluate_btc_option_flow_replay,
)


def test_next_minute_entry_and_ambiguous_bar_choose_stop_first() -> None:
    """Available flow enters at the next minute open and risk wins ties."""
    bars = _bars(4)
    bars.loc[bars.index[1], ["high", "low"]] = [102.1, 98.9]

    replay = evaluate_btc_option_flow_replay(
        bars,
        _flow(long_at=bars.index[1]),
        slippage_bps_per_market_side=0.0,
    )

    trade = replay.report.trades[0]
    assert trade.entry_time_utc == bars.index[1].isoformat()
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.stop_price == pytest.approx(99.0)
    assert trade.target_price == pytest.approx(102.0)
    assert trade.exit_reason == "stop"
    assert trade.same_bar_ambiguous is True


def test_opposing_flow_exit_applies_exact_funding_fees_and_sizing() -> None:
    """The strategic exit must close next-open with V58 costs and sizing."""
    bars = _bars(6)
    bars.loc[bars.index[2], "funding_rate"] = 0.001

    replay = evaluate_btc_option_flow_replay(
        bars,
        _flow(long_at=bars.index[1], opposing_at=bars.index[3]),
        slippage_bps_per_market_side=0.0,
    )

    trade = replay.report.trades[0]
    assert trade.exit_time_utc == bars.index[3].isoformat()
    assert trade.exit_reason == "signal"
    assert trade.notional_usd == pytest.approx(5_000.0)
    assert trade.margin_usd == pytest.approx(500.0)
    assert trade.quantity == pytest.approx(50.0)
    assert trade.funding_cashflow_usd == pytest.approx(-5.0)
    assert trade.fees_usd == pytest.approx(4.5)
    assert trade.net_pnl_usd == pytest.approx(-9.5)


def test_target_uses_maker_fee_and_one_percent_stop_two_percent_target() -> None:
    """A clean target touch must use the frozen 2R barrier and maker fee."""
    bars = _bars(4)
    bars.loc[bars.index[1], ["high", "low", "close"]] = [102.1, 99.5, 102.0]

    replay = evaluate_btc_option_flow_replay(
        bars,
        _flow(long_at=bars.index[1]),
        slippage_bps_per_market_side=0.0,
    )

    trade = replay.report.trades[0]
    assert trade.exit_reason == "target"
    assert trade.exit_price == pytest.approx(102.0)
    assert trade.fees_usd == pytest.approx(2.25 + 50.0 * 102.0 * 0.00015)


def test_twenty_four_hour_fallback_is_wall_clock_based() -> None:
    """A flat lifecycle must close exactly 24 hours after its entry open."""
    bars = _bars(1_443)

    replay = evaluate_btc_option_flow_replay(
        bars,
        _flow(long_at=bars.index[1]),
        slippage_bps_per_market_side=0.0,
    )

    trade = replay.report.trades[0]
    assert trade.exit_reason == "max_hold"
    assert pd.Timestamp(trade.exit_time_utc) - pd.Timestamp(trade.entry_time_utc) == (
        pd.Timedelta(hours=24)
    )


def test_extra_delay_and_entry_partition_are_applied_before_routing() -> None:
    """Scenario delay and entry-time partitions must not shift retrospectively."""
    bars = _bars(20)
    flow = _flow(long_at=bars.index[1])

    delayed = evaluate_btc_option_flow_replay(
        bars,
        flow,
        slippage_bps_per_market_side=0.0,
        extra_delay_minutes=5,
    )
    excluded = evaluate_btc_option_flow_replay(
        bars,
        flow,
        slippage_bps_per_market_side=0.0,
        entry_start_utc=bars.index[2],
    )

    assert delayed.report.trades[0].entry_time_utc == bars.index[6].isoformat()
    assert excluded.report.completed_trades == 0


def test_open_position_prevents_overlap_and_requires_reset_before_reentry() -> None:
    """Repeated onsets cannot overlap and a later reset permits a new lifecycle."""
    bars = _bars(12)
    flow = pd.DataFrame(
        {
            "available_at": [
                bars.index[1],
                bars.index[2],
                bars.index[4],
                bars.index[6],
            ],
            "long_onset": [True, True, False, True],
            "opposing_onset": [False, False, True, False],
        }
    )

    replay = evaluate_btc_option_flow_replay(
        bars,
        flow,
        slippage_bps_per_market_side=0.0,
    )

    assert replay.report.maximum_concurrent_positions == 1
    assert replay.report.completed_trades == 2
    assert replay.report.trades[0].exit_reason == "signal"


def test_displaced_count_excludes_onsets_outside_entry_and_execution_windows() -> None:
    """Routing diagnostics must count only signals relevant to the replay slice."""
    bars = _bars(12).drop(index=pd.Timestamp("2025-01-01T00:04:00Z"))
    flow = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2024-12-31T20:00:00Z", "2025-01-01T00:05:00Z"]
            ),
            "long_onset": [True, True],
            "opposing_onset": [False, False],
        }
    )

    replay = evaluate_btc_option_flow_replay(
        bars,
        flow,
        slippage_bps_per_market_side=0.0,
        entry_start_utc=pd.Timestamp("2025-01-01T00:02:00Z"),
        entry_end_utc=pd.Timestamp("2025-01-01T00:10:00Z"),
    )

    assert replay.displaced_signal_count == 1
    assert replay.long_signal_count == 0


def _bars(minutes: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=minutes, freq="1min")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "funding_rate": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )


def _flow(
    *,
    long_at: pd.Timestamp,
    opposing_at: pd.Timestamp | None = None,
) -> pd.DataFrame:
    available = [long_at]
    long = [True]
    opposing = [False]
    if opposing_at is not None:
        available.append(opposing_at)
        long.append(False)
        opposing.append(True)
    return pd.DataFrame(
        {
            "available_at": available,
            "long_onset": long,
            "opposing_onset": opposing,
        }
    )
