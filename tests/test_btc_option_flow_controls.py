"""Tests for frozen BTC option-flow placebo and sweep controls."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.btc_option_flow_controls import (
    direction_inverted_placebo_flow,
    evaluate_btc_option_flow_sweep_control,
)


def test_direction_inverted_placebo_swaps_entry_and_strategic_exit() -> None:
    """The placebo must reverse only extreme direction, not timing."""
    flow = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2025-01-01T01:01:00Z", "2025-01-01T02:01:00Z"]
            ),
            "long_onset": [True, False],
            "opposing_onset": [False, True],
        }
    )

    placebo = direction_inverted_placebo_flow(flow)

    assert placebo["available_at"].equals(flow["available_at"])
    assert placebo["long_onset"].tolist() == [False, True]
    assert placebo["opposing_onset"].tolist() == [True, False]


def test_sweep_control_uses_exact_target_cost_and_delay() -> None:
    """The unchanged sweep arm must retain its 60-bps target and scenario delay."""
    execution = _bars(10)
    execution.loc[execution.index[6], ["high", "close"]] = [100.7, 100.6]
    control = pd.DataFrame(
        {
            "long_entry": [True] + [False] * 9,
            "short_entry": False,
            "long_exit": False,
            "short_exit": False,
            "long_signal_name": "liquidity_sweep_long_1h_stop60_target60_v2",
        },
        index=execution.index,
    )

    def builder(_: pd.DataFrame) -> SimpleNamespace:
        return SimpleNamespace(control=control)

    replay = evaluate_btc_option_flow_sweep_control(
        execution,
        execution,
        slippage_bps_per_market_side=0.0,
        extra_delay_minutes=5,
        signal_builder=builder,
    )

    trade = replay.report.trades[0]
    assert trade.entry_time_utc == execution.index[6].isoformat()
    assert trade.target_price == pytest.approx(100.6)
    assert trade.stop_price == pytest.approx(99.4)
    assert trade.exit_reason == "target"
    assert replay.raw_signal_count == 1
    assert replay.scheduled_signal_count == 1
    assert replay.displaced_signal_count == 0


def _bars(minutes: int) -> pd.DataFrame:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=minutes, freq="1min")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
            "funding_rate": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )
