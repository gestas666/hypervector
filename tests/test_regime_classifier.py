"""Causal regime classifier and multi-timeframe composition tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.composite import compose_regimes, classify_multitimeframe


def _bars(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close), freq="1min", tz="UTC")
    values = close.astype(float)
    volumes = np.full(len(values), 100.0) if volume is None else volume.astype(float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.02,
            "low": values - 0.02,
            "close": values,
            "volume": volumes,
        },
        index=index,
    )


def _config() -> RegimeClassifierConfig:
    return RegimeClassifierConfig(
        ema_fast=3,
        ema_slow=8,
        warmup_bars=10,
        structure_lookback=10,
        trend_strength_percentile=50.0,
        range_strength_percentile=20.0,
        minimum_trend_gap_bps=1.0,
        choppiness_length=5,
        choppiness_range_threshold=65.0,
        breakout_lookback=5,
        breakout_clearance_bps=1.0,
        breakout_volume_lookback=5,
        breakout_volume_multiple=1.5,
    )


def test_classifier_emits_trend_up_and_down() -> None:
    upward = classify_timeframe(_bars(np.linspace(100.0, 110.0, 80)), _config())
    downward = classify_timeframe(_bars(np.linspace(110.0, 100.0, 80)), _config())

    assert upward.iloc[-1].primary_regime == "TREND_UP"
    assert downward.iloc[-1].primary_regime == "TREND_DOWN"


def test_classifier_emits_range_for_flat_structure() -> None:
    close = 100.0 + np.sin(np.arange(80) * np.pi / 2.0) * 0.002

    result = classify_timeframe(_bars(close), _config())

    assert result.iloc[-1].primary_regime == "RANGE"
    assert bool(result.iloc[-1].coiling) is True


def test_compression_alone_is_not_a_breakout() -> None:
    result = classify_timeframe(_bars(np.full(80, 100.0)), _config())

    assert "BREAKOUT" not in set(result.primary_regime.iloc[-20:])


def test_classifier_requires_directional_prior_range_break() -> None:
    base = np.full(30, 100.0)
    high_volume = np.full(30, 100.0)
    high_volume[-1] = 500.0
    upward = base.copy()
    upward[-1] = 100.25
    downward = base.copy()
    downward[-1] = 99.75

    up_result = classify_timeframe(_bars(upward, high_volume), _config())
    down_result = classify_timeframe(_bars(downward, high_volume), _config())

    assert up_result.iloc[-1].primary_regime == "BREAKOUT"
    assert up_result.iloc[-1].breakout_direction == "BK_UPWARD"
    assert down_result.iloc[-1].primary_regime == "BREAKOUT"
    assert down_result.iloc[-1].breakout_direction == "BK_DOWNWARD"


def test_classifier_warmup_is_unknown() -> None:
    result = classify_timeframe(_bars(np.linspace(100.0, 101.0, 20)), _config())

    assert set(result.primary_regime.iloc[:9]) == {"UNKNOWN"}


def test_classifier_is_prefix_invariant() -> None:
    bars = _bars(100.0 + np.sin(np.arange(100) / 7.0))

    prefix = classify_timeframe(bars.iloc[:70], _config())
    full = classify_timeframe(bars, _config())

    pd.testing.assert_frame_equal(prefix, full.iloc[:70])


def _state_frame(
    index: pd.DatetimeIndex,
    primary: str,
    breakout: str | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": primary,
            "breakout_direction": breakout,
            "confidence": 1.0,
            "reason": "fixture",
            "coiling": False,
        },
        index=index,
    )


def test_composite_uses_5m_as_primary_without_15m_hard_veto() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_DOWN"),
    )

    assert set(result.primary_regime) == {"TREND_UP"}
    assert set(result.context_15m) == {"TREND_DOWN"}
    assert set(result.reason) == {"5m_primary_trend"}


def test_confirmed_1m_and_5m_breakout_overrides_stale_15m() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "BREAKOUT", "BK_UPWARD"),
        _state_frame(index, "BREAKOUT", "BK_UPWARD"),
        _state_frame(index, "TREND_DOWN"),
    )

    assert set(result.primary_regime) == {"BREAKOUT"}
    assert set(result.breakout_direction) == {"BK_UPWARD"}
    assert set(result.reason) == {"confirmed_1m_5m_breakout"}


def test_5m_range_remains_no_entry_state() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "RANGE"),
        _state_frame(index, "TREND_UP"),
    )

    assert set(result.primary_regime) == {"RANGE"}


def test_multitimeframe_context_uses_only_completed_htf_bars() -> None:
    bars = _bars(np.linspace(100.0, 110.0, 121))
    changed = bars.copy()
    changed.iloc[-1, changed.columns.get_loc("close")] = 80.0
    changed.iloc[-1, changed.columns.get_loc("low")] = 79.9

    original = classify_multitimeframe(bars, _config())
    mutated = classify_multitimeframe(changed, _config())

    assert original.iloc[-1].state_5m == mutated.iloc[-1].state_5m
    assert original.iloc[-1].context_15m == mutated.iloc[-1].context_15m
