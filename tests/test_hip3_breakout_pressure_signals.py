"""Causal HIP-3 breakout plus visible-book pressure signal contracts."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
    build_breakout_pressure_signals,
)


def _bars(
    closes: list[float],
    imbalances: list[float],
    *,
    gaps: list[int] | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=len(closes), freq="15min")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "decision_imbalance_10": imbalances,
            "gap_before_bars": gaps or [0] * len(closes),
            "end_boundary_age_ms": [100] * len(closes),
            "source_snapshot_count": [100] * len(closes),
        },
        index=index,
    )


def _config() -> Hip3BreakoutPressureConfig:
    return Hip3BreakoutPressureConfig(
        breakout_lookback_bars=3,
        fast_ema=2,
        slow_ema=3,
        minimum_abs_imbalance=0.2,
        maximum_stop_bps=80.0,
    )


def test_emits_only_fresh_long_breakout_with_aligned_pressure() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 101.0, 102.0],
        [0.0, 0.0, 0.0, 0.6, 0.7],
    )

    signals = build_breakout_pressure_signals(bars, _config())

    assert signals["long_entry"].tolist() == [False, False, False, True, False]
    assert not signals["short_entry"].any()
    assert signals["entry_direction"].tolist() == [None, None, None, "long", None]
    assert signals["stop_price"].iloc[3] == 100.192
    assert signals["breakout_side"].iloc[3] == "long"


def test_pressure_confirmation_is_symmetric_and_not_optional() -> None:
    long_bars = _bars(
        [100.0, 100.0, 100.0, 101.0],
        [0.0, 0.0, 0.0, -0.6],
    )
    short_bars = _bars(
        [100.0, 100.0, 100.0, 99.0],
        [0.0, 0.0, 0.0, -0.6],
    )

    opposed = build_breakout_pressure_signals(long_bars, _config())
    aligned = build_breakout_pressure_signals(short_bars, _config())

    assert not opposed["long_entry"].any()
    assert aligned["short_entry"].iloc[-1]
    assert aligned["stop_price"].iloc[-1] == 99.792
    assert aligned["breakout_side"].iloc[-1] == "short"


def test_gap_resets_indicator_and_breakout_history() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 101.0, 102.0, 103.0, 104.0],
        [0.5] * 7,
        gaps=[0, 0, 0, 1, 0, 0, 0],
    )

    signals = build_breakout_pressure_signals(bars, _config())

    assert not signals["long_entry"].iloc[3:6].any()
    assert signals["long_entry"].iloc[6]


def test_gap_does_not_retroactively_change_prior_entry_signal() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 101.0, 102.0],
        [0.5] * 5,
        gaps=[0, 0, 0, 0, 2],
    )

    prefix = build_breakout_pressure_signals(bars.iloc[:4], _config())
    signals = build_breakout_pressure_signals(bars, _config())

    assert signals["long_entry"].iloc[3] == prefix["long_entry"].iloc[3]
    assert signals["stop_price"].iloc[3] == prefix["stop_price"].iloc[3]
    assert not signals["entry_expired_across_gap"].any()
    assert signals["gap_recovery_exit"].iloc[4]
    assert signals["long_exit"].iloc[4]
    assert signals["short_exit"].iloc[4]


def test_future_prices_cannot_change_prior_signals() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 101.0, 102.0, 103.0],
        [0.0, 0.0, 0.0, 0.6, 0.7, 0.8],
    )
    changed = bars.copy()
    changed.loc[changed.index[-1], ["open", "high", "low", "close"]] = [
        50.0,
        50.1,
        49.9,
        50.0,
    ]

    original = build_breakout_pressure_signals(bars, _config())
    revised = build_breakout_pressure_signals(changed, _config())

    pd.testing.assert_frame_equal(original.iloc[:-1], revised.iloc[:-1])


def test_signal_identity_uses_explicit_timeframe() -> None:
    bars = _bars(
        [100.0, 100.0, 100.0, 101.0],
        [0.0, 0.0, 0.0, 0.6],
    )

    signals = build_breakout_pressure_signals(bars, _config(), timeframe="5m")

    assert (
        signals.loc[signals["long_entry"], "signal_name"]
        .eq("hip3_breakout_pressure_long@5m")
        .all()
    )
