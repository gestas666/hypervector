"""Tests for literal Swing Auto execution on a Heikin-Ashi chart."""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_series_equal

from hypervector.research.swing_ha_chart_signals import (
    build_swing_ha_chart_signals,
)
from hypervector.research.swing_ha_signals import (
    SwingHaSignalConfig,
    build_heikin_ashi,
    confirmed_pivot_levels,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=12, freq="15min", tz="UTC")
    close = [100, 103, 101, 106, 104, 109, 105, 102, 99, 96, 98, 94]
    return pd.DataFrame(
        {
            "open": [100, 100, 103, 101, 106, 104, 109, 105, 102, 99, 96, 98],
            "high": [102, 104, 104, 107, 107, 110, 110, 106, 103, 100, 99, 99],
            "low": [99, 99, 100, 100, 103, 103, 104, 101, 98, 95, 95, 93],
            "close": close,
            "volume": [10.0] * 12,
        },
        index=index,
    )


def test_chart_signals_compute_ema_and_pivots_from_heikin_ashi_domain() -> None:
    bars = _bars()
    config = SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1)

    signals = build_swing_ha_chart_signals(bars, config)
    chart = build_heikin_ashi(bars).rename(
        columns={
            "ha_open": "open",
            "ha_high": "high",
            "ha_low": "low",
            "ha_close": "close",
        }
    )
    expected_fast = chart["close"].ewm(span=2, adjust=False, min_periods=2).mean()
    expected_pivots = confirmed_pivot_levels(chart, pivot_length=1)

    assert_series_equal(signals["ema_fast"], expected_fast, check_names=False)
    assert_series_equal(
        signals["last_pivot_high"],
        expected_pivots["last_pivot_high"],
        check_names=False,
    )
    raw_fast = bars["close"].ewm(span=2, adjust=False, min_periods=2).mean()
    assert not signals["ema_fast"].equals(raw_fast)


def test_literal_state_rule_holds_only_while_signal_and_color_align() -> None:
    bars = _bars()
    config = SwingHaSignalConfig(
        fast_ema=2,
        slow_ema=3,
        pivot_length=1,
        entry_mode="state",
        exit_mode="alignment_loss",
    )

    signals = build_swing_ha_chart_signals(bars, config)

    assert signals["long_entry"].equals(
        signals["buy_state"] & signals["ha_color"].eq(1)
    )
    assert signals["short_entry"].equals(
        signals["sell_state"] & signals["ha_color"].eq(-1)
    )
    assert signals["long_exit"].equals(~signals["long_alignment"])
    assert signals["short_exit"].equals(~signals["short_alignment"])
    assert set(signals["signal_price_domain"]) == {"heikin_ashi_chart"}


def test_chart_signal_builder_does_not_replace_raw_execution_prices() -> None:
    bars = _bars()
    before = bars.copy(deep=True)

    build_swing_ha_chart_signals(
        bars,
        SwingHaSignalConfig(fast_ema=2, slow_ema=3, pivot_length=1),
    )

    pd.testing.assert_frame_equal(bars, before)
