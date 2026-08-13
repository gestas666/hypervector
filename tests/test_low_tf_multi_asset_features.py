"""Causal feature tests for bidirectional multi-asset research."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.low_tf_multi_asset_features import (
    LowTfFeatureConfig,
    build_low_tf_features,
)


def _bars(rows: int = 90) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC")
    position = np.arange(rows, dtype=float)
    close = 100.0 + position * 0.08 + np.sin(position / 3.0)
    opening = close - np.cos(position / 4.0) * 0.2
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "open": opening,
            "high": np.maximum(opening, close) + 0.5 + position * 0.001,
            "low": np.minimum(opening, close) - 0.4 - position * 0.001,
            "close": close,
            "volume": 10.0 + position,
        }
    )


def _small_config() -> LowTfFeatureConfig:
    return LowTfFeatureConfig(
        range_lookback=3,
        breakout_lookback=2,
        ema_fast=2,
        ema_slow=3,
        bbwp_length=2,
        bbwp_lookback=5,
        bbwp_signal=2,
        rsi_length=2,
        rsi_signal=2,
        pmarp_ema=2,
        pmarp_lookback=5,
        pmarp_signal=2,
        atr_length=2,
    )


def test_prior_boundaries_exclude_the_current_decision_bar() -> None:
    bars = _bars(12)
    features = build_low_tf_features(bars, _small_config())
    row = features.iloc[5]

    assert row["range_high_240"] == pytest.approx(bars["high"].iloc[2:5].max())
    assert row["range_low_240"] == pytest.approx(bars["low"].iloc[2:5].min())
    assert row["breakout_high_120"] == pytest.approx(bars["high"].iloc[3:5].max())
    assert row["breakout_low_120"] == pytest.approx(bars["low"].iloc[3:5].min())
    assert row["range_midpoint_240"] == pytest.approx(
        (bars["high"].iloc[2:5].max() + bars["low"].iloc[2:5].min()) / 2.0
    )


def test_context_is_visible_only_after_completed_fifteen_minute_close() -> None:
    features = build_low_tf_features(_bars(9), _small_config())

    assert features["context_bar_open_at"].iloc[:2].isna().all()
    assert features["context_bar_open_at"].iloc[2] == pd.Timestamp(
        "2026-01-01 00:00", tz="UTC"
    )
    assert features["context_bar_open_at"].iloc[4] == pd.Timestamp(
        "2026-01-01 00:00", tz="UTC"
    )
    assert features["context_bar_open_at"].iloc[5] == pd.Timestamp(
        "2026-01-01 00:15", tz="UTC"
    )


def test_feature_frame_contains_declared_causal_components() -> None:
    features = build_low_tf_features(_bars(), _small_config())

    required = {
        "ema_fast_5m",
        "ema_slow_5m",
        "ema_fast_15m",
        "ema_slow_15m",
        "context_direction",
        "context_fast_slope_bps",
        "bbwp_percentile",
        "bbwp_signal",
        "rsi",
        "rsi_signal",
        "rsi_bearish_divergence",
        "rsi_bullish_divergence",
        "pmarp",
        "pmarp_signal",
        "atr",
    }
    assert required.issubset(features.columns)
    assert set(features["context_direction"].unique()).issubset({-1, 0, 1})
    assert np.isfinite(features["atr"].dropna()).all()


def test_features_are_append_invariant_at_completed_decision_times() -> None:
    bars = _bars(93)
    prefix = bars.iloc[:90].copy()
    before = build_low_tf_features(prefix, _small_config())
    after = (
        build_low_tf_features(bars, _small_config()).iloc[:90].reset_index(drop=True)
    )

    pd.testing.assert_frame_equal(before, after)


def test_default_feature_identity_matches_frozen_plan() -> None:
    config = LowTfFeatureConfig()

    assert config.range_lookback == 240
    assert config.breakout_lookback == 120
    assert (config.ema_fast, config.ema_slow) == (21, 55)
    assert (config.bbwp_length, config.bbwp_lookback, config.bbwp_signal) == (
        20,
        240,
        5,
    )
    assert (config.rsi_length, config.rsi_signal) == (14, 7)
    assert (config.pmarp_ema, config.pmarp_lookback, config.pmarp_signal) == (
        21,
        350,
        7,
    )
    assert config.atr_length == 14


def test_invalid_feature_input_fails_instead_of_filling_unknowns() -> None:
    bars = _bars(10)
    bars.loc[3, "close"] = np.nan

    with pytest.raises(ValueError, match="finite"):
        build_low_tf_features(bars, _small_config())


def test_invalid_feature_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        LowTfFeatureConfig(range_lookback=0)
