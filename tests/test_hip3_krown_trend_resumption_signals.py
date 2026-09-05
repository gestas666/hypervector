"""Causal contract tests for the predeclared BRENTOIL Krown challenger."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hip3_krown_trend_resumption_signals import (
    Hip3KrownTrendResumptionConfig,
    build_hip3_krown_trend_resumption_signals,
)


def _bars(close: np.ndarray) -> pd.DataFrame:
    """Return one gap-free completed 15-minute source frame."""
    index = pd.date_range("2026-01-01", periods=len(close), freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "close": close,
            "gap_before_bars": np.zeros(len(close), dtype=int),
        },
        index=index,
    )


def _long_path() -> np.ndarray:
    """Return an uptrend, completed pullback, and resumption path."""
    return np.concatenate(
        [
            np.linspace(100.0, 116.0, 80),
            np.linspace(116.0, 114.0, 12),
            np.linspace(114.0, 121.0, 28),
        ]
    )


def test_default_contract_matches_preregistered_pine_lengths() -> None:
    """Default RSI/EMA values must remain bound to the frozen source contract."""
    config = Hip3KrownTrendResumptionConfig()

    assert config.rsi_length == 14
    assert config.rsi_ema_length == 12
    assert config.price_ema_fast == 21
    assert config.price_ema_slow == 55
    assert config.maximum_hold_bars == 96
    assert config.protective_stop_bps == 80.0


def test_fresh_long_turn_is_emitted_once_and_exposes_completed_evidence() -> None:
    """A rising Krown color turn inside an uptrend must be an onset, not a state."""
    signals = build_hip3_krown_trend_resumption_signals(_bars(_long_path()))
    entries = signals.loc[signals["long_entry"]]

    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["entry_direction"] == "long"
    assert row["signal_name"] == "hip3_krown_trend_resumption_long@15m"
    assert row["close"] > row["ema_fast"] > row["ema_slow"]
    assert row["rsi"] > row["rsi_ema"] >= 50.0
    assert row["rsi_ema_slope"] > 0.0
    assert bool(row["long_exit"]) is False


def test_short_contract_is_symmetric() -> None:
    """Price inversion must produce the corresponding short onset contract."""
    close = 240.0 - _long_path()
    signals = build_hip3_krown_trend_resumption_signals(_bars(close))
    entries = signals.loc[signals["short_entry"]]

    assert len(entries) == 1
    row = entries.iloc[0]
    assert row["entry_direction"] == "short"
    assert row["signal_name"] == "hip3_krown_trend_resumption_short@15m"
    assert row["close"] < row["ema_fast"] < row["ema_slow"]
    assert row["rsi"] < row["rsi_ema"] <= 50.0
    assert row["rsi_ema_slope"] < 0.0


def test_appended_future_rows_cannot_rewrite_signal_prefix() -> None:
    """Appending later bars must leave every earlier decision byte-equivalent."""
    original = _bars(_long_path())
    future = _bars(np.concatenate([_long_path(), np.linspace(121.0, 90.0, 20)]))

    left = build_hip3_krown_trend_resumption_signals(original)
    right = build_hip3_krown_trend_resumption_signals(future).loc[original.index]

    pd.testing.assert_frame_equal(left, right)


def test_gap_recovery_censors_entry_and_forces_open_side_exits() -> None:
    """An unknown interval must reset indicators and close rather than infer continuity."""
    bars = _bars(_long_path())
    recovery = bars.index[-6]
    bars.loc[recovery, "gap_before_bars"] = 3

    signals = build_hip3_krown_trend_resumption_signals(bars)

    assert not bool(signals.loc[recovery, "long_entry"])
    assert not bool(signals.loc[recovery, "short_entry"])
    assert bool(signals.loc[recovery, "long_exit"])
    assert bool(signals.loc[recovery, "short_exit"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rsi_length": 0},
        {"rsi_ema_length": True},
        {"price_ema_fast": 55, "price_ema_slow": 21},
        {"protective_stop_bps": float("nan")},
        {"maximum_hold_bars": 0},
    ],
)
def test_invalid_frozen_parameters_fail_closed(kwargs: dict[str, object]) -> None:
    """Malformed parameters must fail instead of being success-shaped."""
    with pytest.raises(ValueError):
        Hip3KrownTrendResumptionConfig(**kwargs)
