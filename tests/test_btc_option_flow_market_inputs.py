"""Tests for gap-aware BTC option-flow replay market preparation."""

from __future__ import annotations

import pandas as pd

from hypervector.research.btc_option_flow_market_inputs import (
    prepare_gap_aware_option_flow_market,
)


def test_market_preserves_observed_path_and_repairs_only_signal_context() -> None:
    """Execution must see gaps while hourly controls receive labeled continuity."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    expected = pd.date_range(start, periods=6, freq="1min")
    native = _candles(expected.delete([2, 3]))
    funding = pd.Series([0.001], index=pd.DatetimeIndex([start]), name="funding_rate")

    prepared = prepare_gap_aware_option_flow_market(
        native,
        funding,
        start=start,
        end=start + pd.Timedelta(minutes=6),
        maximum_repair_minutes=2,
    )

    assert len(prepared.execution_bars) == 4
    assert prepared.execution_bars.loc[expected[4], "gap_before_bars"] == 2
    assert len(prepared.signal_bars) == 6
    assert prepared.signal_bars["source"].eq("hl_gap_fill").sum() == 2
    assert prepared.execution_bars.loc[start, "funding_rate"] == 0.001
    assert prepared.gap_fill_rows == 2
    assert prepared.maximum_gap_minutes == 2


def test_funding_inside_gap_moves_to_first_observed_bar_after_event() -> None:
    """A funding event in a bounded gap must apply before gap censorship."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    expected = pd.date_range(start, periods=65, freq="1min")
    native = _candles(expected.delete(60))
    funding = pd.Series(
        [0.001, 0.002],
        index=pd.DatetimeIndex([start, start + pd.Timedelta(hours=1)]),
        name="funding_rate",
    )

    prepared = prepare_gap_aware_option_flow_market(
        native,
        funding,
        start=start,
        end=start + pd.Timedelta(minutes=65),
        maximum_repair_minutes=2,
    )

    first_after_gap = start + pd.Timedelta(minutes=61)
    assert prepared.execution_bars.loc[first_after_gap, "gap_before_bars"] == 1
    assert prepared.execution_bars.loc[first_after_gap, "funding_rate"] == 0.002
    assert prepared.funding_events_shifted_after_gap == 1


def _candles(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )
