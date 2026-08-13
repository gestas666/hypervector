"""Tests for the corrected HYPE five-minute impulse-fade replay."""

from __future__ import annotations

import importlib

import pandas as pd
import pytest


def _candidate_module():
    return importlib.import_module("hypervector.research.hype_impulse_5m_candidate")


def _bars(count: int = 40) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * count,
            "high": [100.1] * count,
            "low": [99.9] * count,
            "close": [100.0] * count,
            "volume": [10.0] * count,
            "contains_gap_fill": [False] * count,
        }
    )


def _signal(index: pd.Index, position: int = 0) -> pd.Series:
    values = [False] * len(index)
    values[position] = True
    return pd.Series(values, index=index)


def test_maximum_hold_minutes_are_not_interpreted_as_bar_count() -> None:
    candidate = _candidate_module()

    config = candidate.HypeImpulseConfig(maximum_hold_minutes=23)

    assert candidate.maximum_hold_bars(config) == 5


def test_replay_enters_at_next_bar_open_and_holds_only_five_bars() -> None:
    candidate = _candidate_module()
    bars = _bars(10)
    bars.loc[1, "open"] = 101.0
    bars.loc[1:, ["high", "low", "close"]] = [101.1, 100.9, 101.0]
    atr_bps = pd.Series([10_000.0] * len(bars), index=bars.index)
    config = candidate.HypeImpulseConfig(
        maximum_hold_minutes=23,
        take_profit_atr_multiple=10.0,
        stop_loss_atr_multiple=10.0,
    )

    result = candidate.replay_impulse_signals(
        bars,
        _signal(bars.index),
        atr_bps,
        pd.Series(dtype=float),
        config=config,
        side="long",
        round_trip_cost_bps=0.0,
        partition_start=bars.iloc[0]["timestamp"],
        partition_end=bars.iloc[-1]["timestamp"] + pd.Timedelta(minutes=5),
    )

    trade = result.trades[0]
    assert trade.entry_price == pytest.approx(101.0)
    assert trade.entry_time == bars.iloc[1]["timestamp"]
    assert trade.exit_time == bars.iloc[5]["timestamp"] + pd.Timedelta(minutes=5)
    assert trade.holding_minutes == 25
    assert trade.exit_reason == "maximum_hold"


def test_dual_barrier_touch_resolves_to_stop() -> None:
    candidate = _candidate_module()
    bars = _bars(5)
    bars.loc[1, ["open", "high", "low", "close"]] = [100.0, 101.0, 99.0, 100.0]
    atr_bps = pd.Series([20.0] * len(bars), index=bars.index)
    config = candidate.HypeImpulseConfig(
        take_profit_atr_multiple=2.0,
        stop_loss_atr_multiple=0.5,
    )

    result = candidate.replay_impulse_signals(
        bars,
        _signal(bars.index),
        atr_bps,
        pd.Series(dtype=float),
        config=config,
        side="long",
        round_trip_cost_bps=13.0,
        partition_start=bars.iloc[0]["timestamp"],
        partition_end=bars.iloc[-1]["timestamp"] + pd.Timedelta(minutes=5),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.gross_bps == pytest.approx(-10.0)
    assert trade.net_bps == pytest.approx(-23.0)


def test_positive_funding_is_paid_by_long_position() -> None:
    candidate = _candidate_module()
    bars = _bars(15)
    atr_bps = pd.Series([10_000.0] * len(bars), index=bars.index)
    funding = pd.Series(
        [0.0001],
        index=pd.DatetimeIndex([pd.Timestamp("2026-01-01T01:00:00Z")]),
    )
    config = candidate.HypeImpulseConfig(
        maximum_hold_minutes=65,
        take_profit_atr_multiple=10.0,
        stop_loss_atr_multiple=10.0,
    )

    result = candidate.replay_impulse_signals(
        bars,
        _signal(bars.index),
        atr_bps,
        funding,
        config=config,
        side="long",
        round_trip_cost_bps=13.0,
        partition_start=bars.iloc[0]["timestamp"],
        partition_end=bars.iloc[-1]["timestamp"] + pd.Timedelta(minutes=5),
    )

    trade = result.trades[0]
    assert trade.funding_bps == pytest.approx(-1.0)
    assert trade.net_bps == pytest.approx(-14.0)


def test_gap_crossing_lifecycle_is_censored() -> None:
    candidate = _candidate_module()
    bars = _bars(10)
    bars.loc[3, "contains_gap_fill"] = True
    atr_bps = pd.Series([10_000.0] * len(bars), index=bars.index)

    result = candidate.replay_impulse_signals(
        bars,
        _signal(bars.index),
        atr_bps,
        pd.Series(dtype=float),
        config=candidate.HypeImpulseConfig(maximum_hold_minutes=23),
        side="long",
        round_trip_cost_bps=13.0,
        partition_start=bars.iloc[0]["timestamp"],
        partition_end=bars.iloc[-1]["timestamp"] + pd.Timedelta(minutes=5),
    )

    assert result.trades == ()
    assert result.gap_censored == 1


def test_trade_cannot_cross_partition_boundary() -> None:
    candidate = _candidate_module()
    bars = _bars(10)
    atr_bps = pd.Series([10_000.0] * len(bars), index=bars.index)

    result = candidate.replay_impulse_signals(
        bars,
        _signal(bars.index, 3),
        atr_bps,
        pd.Series(dtype=float),
        config=candidate.HypeImpulseConfig(maximum_hold_minutes=23),
        side="long",
        round_trip_cost_bps=13.0,
        partition_start=bars.iloc[0]["timestamp"],
        partition_end=bars.iloc[6]["timestamp"],
    )

    assert result.trades == ()
    assert result.boundary_censored == 1


def test_one_minute_aggregation_marks_gap_filled_bars() -> None:
    candidate = _candidate_module()
    timestamps = pd.date_range("2026-01-01", periods=10, freq="1min", tz="UTC")
    minute = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(10),
            "high": [value + 1 for value in range(10)],
            "low": [value - 1 for value in range(10)],
            "close": [value + 0.5 for value in range(10)],
            "volume": [1.0] * 10,
            "source": ["hl"] * 7 + ["hl_gap_fill"] + ["hl"] * 2,
        }
    )

    bars = candidate.aggregate_completed_five_minute_bars(minute)

    assert len(bars) == 2
    assert bars.iloc[0].to_dict() == {
        "timestamp": timestamps[0],
        "open": 0.0,
        "high": 5.0,
        "low": -1.0,
        "close": 4.5,
        "volume": 5.0,
        "contains_gap_fill": False,
    }
    assert bool(bars.iloc[1]["contains_gap_fill"])


def test_signals_require_sixty_clean_completed_bars_after_gap() -> None:
    candidate = _candidate_module()
    bars = _bars(125)
    bars.loc[0:70, "close"] = 100.0
    bars.loc[71:, "close"] = 99.0
    bars["open"] = bars["close"]
    bars["high"] = bars["close"] + 0.1
    bars["low"] = bars["close"] - 0.1
    bars.loc[70, "contains_gap_fill"] = True
    config = candidate.HypeImpulseConfig(
        maximum_close_vs_ema21_bps=10_000.0,
        maximum_di_delta=10_000.0,
        maximum_roc_5_pct=10_000.0,
    )

    signals, _ = candidate.build_impulse_signals(bars, config=config, side="long")

    assert not signals.iloc[70:].any()
