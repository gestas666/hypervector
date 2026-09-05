"""Frozen-contract tests for the 15-minute EMA-speed challenger."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.ema_speed_continuation import (
    EmaSpeedContinuationConfig,
    build_ema_speed_signals,
)


def test_frozen_config_rejects_post_registration_retuning() -> None:
    """The first experiment must not become an implicit parameter grid."""
    config = EmaSpeedContinuationConfig()
    assert config.symbols == ("BTC", "SOL")
    assert config.ema_periods == (5, 21, 55)
    assert config.maximum_hold_bars == 16
    with pytest.raises(ValueError, match="frozen EMA periods"):
        EmaSpeedContinuationConfig(ema_periods=(8, 21, 55))
    with pytest.raises(ValueError, match="frozen symbols"):
        EmaSpeedContinuationConfig(symbols=("BTC",))


def test_long_signal_is_fresh_cross_with_causal_stop() -> None:
    """A trend-aligned recovery enters once and excludes the signal bar from stop."""
    bars = _trend_bars("long")
    signals = build_ema_speed_signals(bars, EmaSpeedContinuationConfig())
    entries = signals.index[signals["long_entry"]]
    assert list(entries) == [bars.index[66]]
    signal_time = entries[0]
    prior_low = float(bars.loc[bars.index[58:66], "low"].min())
    clamp = float(bars.loc[signal_time, "close"]) * (1.0 - 0.008)
    assert signals.loc[signal_time, "stop_price"] == pytest.approx(
        max(prior_low, clamp)
    )
    assert not bool(signals.loc[signal_time, "short_entry"])
    assert signals.loc[signal_time, "long_signal_name"].endswith("@15m")


def test_short_signal_and_exit_are_symmetric() -> None:
    """The short arm uses the mirrored fresh cross and opposite EMA5 exit."""
    bars = _trend_bars("short")
    signals = build_ema_speed_signals(bars, EmaSpeedContinuationConfig())
    entries = signals.index[signals["short_entry"]]
    assert list(entries) == [bars.index[66]]
    assert bool(signals.loc[bars.index[65], "short_exit"])
    assert not bool(signals.loc[bars.index[66], "long_entry"])


def test_future_rows_cannot_change_prior_signal_bytes() -> None:
    """Appending out-of-window bars must not alter the frozen causal prefix."""
    bars = _trend_bars("long")
    config = EmaSpeedContinuationConfig()
    baseline = build_ema_speed_signals(bars, config)
    future = bars.iloc[[-1]].copy()
    future.index = pd.DatetimeIndex([bars.index[-1] + pd.Timedelta(minutes=15)])
    future.loc[:, ["open", "high", "low", "close"]] *= 0.5
    extended = build_ema_speed_signals(pd.concat([bars, future]), config)
    pd.testing.assert_frame_equal(
        baseline,
        extended.loc[baseline.index],
        check_freq=False,
    )


def test_incomplete_source_bar_resets_signal_warmup() -> None:
    """A source gap cannot be bridged by EMA state or manufacture an entry."""
    bars = _trend_bars("long")
    bars.loc[bars.index[64], "source_complete"] = False
    bars.loc[bars.index[64], ["open", "high", "low", "close"]] = float("nan")
    signals = build_ema_speed_signals(bars, EmaSpeedContinuationConfig())
    assert not bool(signals.loc[bars.index[66], "long_entry"])
    assert signals.loc[bars.index[66], "signal_state"] == "warming_after_gap"


def _trend_bars(side: str) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=70, freq="15min", tz="UTC")
    closes = pd.Series([100.0 + 0.2 * value for value in range(70)], index=index)
    if side == "long":
        closes.iloc[65] = closes.iloc[64] - 1.2
        closes.iloc[66] = closes.iloc[64] + 0.8
    else:
        closes = 220.0 - closes
        closes.iloc[65] = closes.iloc[64] + 1.2
        closes.iloc[66] = closes.iloc[64] - 0.8
    frame = pd.DataFrame(index=index)
    frame["close"] = closes
    frame["open"] = closes.shift(1).fillna(closes.iloc[0])
    frame["high"] = frame[["open", "close"]].max(axis=1) + 0.25
    frame["low"] = frame[["open", "close"]].min(axis=1) - 0.25
    frame["source_complete"] = True
    return frame
