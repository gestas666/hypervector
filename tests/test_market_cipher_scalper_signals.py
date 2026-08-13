"""Tests for the recovered prompt-only MC 15m Scalper contract."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd

from hypervector.research.market_cipher_scalper_signals import (
    evaluate_mc_scalper_signals,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Return one bullish WaveTrend decision with minimum score seven."""
    index = pd.date_range("2026-01-01", periods=6, freq="15min", tz=UTC)
    bars = pd.DataFrame(
        {
            "open": np.full(6, 100.0),
            "high": np.full(6, 101.0),
            "low": np.full(6, 99.0),
            "close": np.full(6, 100.5),
        },
        index=index,
    )
    components = pd.DataFrame(
        {
            "wave_cross": [0, 0, 0, 0, 0, 1],
            "money_flow_direction": [0, 0, 0, 1, 0, 0],
            "price_vwap_alignment": [1, 1, 1, 1, 1, 1],
            "volume_ratio": [1.1, 1.1, 1.1, 1.1, 1.1, 1.2],
            "volume_surge": [False] * 6,
            "stoch_k": [50.0, 50.0, 50.0, 50.0, 50.0, 10.0],
        },
        index=index,
    )
    one_hour = pd.Series(np.zeros(6, dtype=np.int8), index=index)
    near_level = pd.Series([False] * 6, index=index, dtype="boolean")
    return bars, components, one_hour, near_level


def test_minimum_seven_point_long_uses_money_flow_sign_within_three_bars() -> None:
    """Money flow is its Pine area sign, not a Green Dot or Red X alias."""
    bars, components, one_hour, near_level = _inputs()

    decisions = evaluate_mc_scalper_signals(bars, components, one_hour, near_level)

    decision = decisions.iloc[0]
    assert decision["side"] == "long"
    assert decision["money_flow_confirmed"]
    assert decision["score"] == 7
    assert decision["eligible"]
    assert decision["stop_anchor"] == 99.0


def test_required_volume_and_major_level_are_fail_closed() -> None:
    """Required unavailable/false conditions cannot become free confluence."""
    bars, components, one_hour, near_level = _inputs()
    components.iloc[-1, components.columns.get_loc("volume_ratio")] = 1.0
    near_level.iloc[-1] = pd.NA

    decisions = evaluate_mc_scalper_signals(bars, components, one_hour, near_level)

    decision = decisions.iloc[0]
    assert not decision["volume_confirmed"]
    assert not decision["htf_level_clear"]
    assert not decision["eligible"]
    assert "volume_not_above_average" in decision["reason"]
    assert "htf_level_unavailable" in decision["reason"]


def test_opposite_one_hour_trend_vetoes_without_erasing_the_decision() -> None:
    """A veto remains visible in telemetry instead of silently dropping a cross."""
    bars, components, one_hour, near_level = _inputs()
    one_hour.iloc[-1] = -1

    decisions = evaluate_mc_scalper_signals(bars, components, one_hour, near_level)

    decision = decisions.iloc[0]
    assert decision["score"] == 7
    assert not decision["eligible"]
    assert decision["reason"] == "opposite_1h_trend"


def test_volume_surge_and_aligned_one_hour_context_add_declared_points() -> None:
    """Optional confluence must add exactly its documented score."""
    bars, components, one_hour, near_level = _inputs()
    components.iloc[-1, components.columns.get_loc("volume_ratio")] = 1.6
    components.iloc[-1, components.columns.get_loc("volume_surge")] = True
    one_hour.iloc[-1] = 1

    decision = evaluate_mc_scalper_signals(bars, components, one_hour, near_level).iloc[
        0
    ]

    assert decision["score"] == 10
    assert decision["eligible"]
