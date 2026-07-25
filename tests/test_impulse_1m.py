"""Unit tests for 1m Impulse strategy port."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.strategies.impulse_1m import build_impulse_1m_signals
from hypervector.regime.detectors import detect_regime_ema
from hypervector.strategies.registry import get_strategy


def test_impulse_1m_signal_generation():
    # Build synthetic 1m OHLCV dataframe
    n = 100
    dates = pd.date_range("2026-01-01", periods=n, freq="1min")
    close = 65000.0 + np.sin(np.linspace(0, 10, n)) * 200.0
    df = pd.DataFrame(
        {
            "open": close - 10.0,
            "high": close + 20.0,
            "low": close - 20.0,
            "close": close,
            "volume": 100.0,
        },
        index=dates,
    )

    entries_l, exits_l, tag_l = build_impulse_1m_signals(df, direction="long")
    assert isinstance(entries_l, pd.Series)
    assert isinstance(exits_l, pd.Series)
    assert tag_l == "impulse_1m_long"

    entries_s, exits_s, tag_s = build_impulse_1m_signals(df, direction="short")
    assert isinstance(entries_s, pd.Series)
    assert isinstance(exits_s, pd.Series)
    assert tag_s == "impulse_1m_short"


def test_impulse_1m_registry():
    from hypervector.strategies import register_all_strategies

    register_all_strategies()
    spec_l = get_strategy("impulse_1m_long")
    assert spec_l.name == "impulse_1m_long"
    assert spec_l.role == "uptrend"

    spec_s = get_strategy("impulse_1m_short")
    assert spec_s.name == "impulse_1m_short"
    assert spec_s.role == "downtrend"


def test_impulse_range_only_masks_non_range_entries():
    """Range variants must not emit entries during directional labels."""
    n = 180
    dates = pd.date_range("2026-01-01", periods=n, freq="1min")
    close = pd.Series(
        65_000.0 + np.sin(np.linspace(0, 18, n)) * 500.0,
        index=dates,
    )
    df = pd.DataFrame(
        {
            "open": close,
            "high": close + 20.0,
            "low": close - 20.0,
            "close": close,
            "volume": 100.0,
        },
        index=dates,
    )
    labels = detect_regime_ema(close, fast=3, slow=8, range_band=0.0001)

    entries, _, tag = build_impulse_1m_signals(
        df,
        direction="long",
        long_ema=1_000_000.0,
        long_di=1_000_000.0,
        long_roc=1_000_000.0,
        range_only=True,
        regime_fast=3,
        regime_slow=8,
        regime_band=0.0001,
    )

    assert entries[labels != "range"].sum() == 0
    assert entries[labels == "range"].sum() > 0
    assert tag == "impulse_1m_range_long"


def test_impulse_range_variants_are_registered():
    """Range policy exposes separate long and short research components."""
    from hypervector.strategies import register_all_strategies

    register_all_strategies()

    long_spec = get_strategy("impulse_1m_range_long")
    short_spec = get_strategy("impulse_1m_range_short")
    assert long_spec.role == "regime"
    assert short_spec.role == "regime"
