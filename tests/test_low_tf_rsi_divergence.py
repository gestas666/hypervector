"""Causal five-bar RSI divergence tests for low-timeframe research."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research import low_tf_rsi_divergence as divergence
from hypervector.research.low_tf_rsi_divergence import (
    confirmed_regular_rsi_divergence,
)


def _series(values: list[float]) -> pd.Series:
    """Return a float series with stable integer positions."""
    return pd.Series(values, dtype=float)


def test_bearish_divergence_emits_on_second_right_confirmation_bar() -> None:
    highs = _series([1, 2, 10, 2, 1, 2, 12, 2, 1])
    lows = highs - 1.0
    rsi = _series([50, 55, 75, 55, 50, 55, 65, 55, 50])

    result = confirmed_regular_rsi_divergence(highs, lows, rsi)

    assert not result["rsi_bearish_divergence"].iloc[:8].any()
    assert bool(result["rsi_bearish_divergence"].iloc[8])
    assert not result["rsi_bullish_divergence"].any()


def test_bullish_divergence_emits_on_second_right_confirmation_bar() -> None:
    lows = _series([10, 9, 2, 9, 10, 9, 1, 9, 10])
    highs = lows + 1.0
    rsi = _series([50, 45, 20, 45, 50, 45, 25, 45, 50])

    result = confirmed_regular_rsi_divergence(highs, lows, rsi)

    assert not result["rsi_bullish_divergence"].iloc[:8].any()
    assert bool(result["rsi_bullish_divergence"].iloc[8])
    assert not result["rsi_bearish_divergence"].any()


def test_divergence_requires_source_rsi_zones() -> None:
    highs = _series([1, 2, 10, 2, 1, 2, 12, 2, 1])
    lows = highs - 1.0
    rsi = _series([50, 52, 59, 52, 50, 52, 58, 52, 50])

    result = confirmed_regular_rsi_divergence(highs, lows, rsi)

    assert not result["rsi_bearish_divergence"].any()


def test_divergence_is_append_invariant() -> None:
    highs = _series([1, 2, 10, 2, 1, 2, 12, 2, 1, 20, 21])
    lows = highs - 1.0
    rsi = _series([50, 55, 75, 55, 50, 55, 65, 55, 50, 80, 81])

    before = confirmed_regular_rsi_divergence(
        highs.iloc[:9], lows.iloc[:9], rsi.iloc[:9]
    )
    after = confirmed_regular_rsi_divergence(highs, lows, rsi).iloc[:9]

    pd.testing.assert_frame_equal(before, after)


def test_divergence_rejects_misaligned_or_nonfinite_inputs() -> None:
    with pytest.raises(ValueError, match="same length"):
        confirmed_regular_rsi_divergence(
            _series([1, 2]), _series([1]), _series([50, 51])
        )
    with pytest.raises(ValueError, match="finite"):
        confirmed_regular_rsi_divergence(
            _series([1, 2, 3]), _series([0, 1, 2]), _series([50, float("nan"), 52])
        )


def test_three_drive_bearish_emits_only_after_third_confirmed_peak() -> None:
    highs = _series([1, 2, 10, 2, 1, 2, 12, 2, 1, 2, 14, 2, 1])
    lows = highs - 1.0
    rsi = _series([50, 55, 75, 55, 50, 55, 70, 55, 50, 55, 65, 55, 50])

    result = divergence.confirmed_three_drive_rsi_divergence(highs, lows, rsi)

    assert not result["rsi_three_drive_bearish"].iloc[:12].any()
    assert bool(result["rsi_three_drive_bearish"].iloc[12])
    assert result["bearish_stop_anchor"].iloc[12] == 14.0
    assert not result["rsi_three_drive_bullish"].any()


def test_three_drive_bullish_emits_only_after_third_confirmed_trough() -> None:
    lows = _series([10, 9, 3, 9, 10, 9, 2, 9, 10, 9, 1, 9, 10])
    highs = lows + 1.0
    rsi = _series([50, 45, 20, 45, 50, 45, 25, 45, 50, 45, 28, 45, 50])

    result = divergence.confirmed_three_drive_rsi_divergence(highs, lows, rsi)

    assert not result["rsi_three_drive_bullish"].iloc[:12].any()
    assert bool(result["rsi_three_drive_bullish"].iloc[12])
    assert result["bullish_stop_anchor"].iloc[12] == 1.0
    assert not result["rsi_three_drive_bearish"].any()
