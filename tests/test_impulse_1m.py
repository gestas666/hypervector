"""Unit tests for 1m Impulse strategy port."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.strategies.impulse_1m import build_impulse_1m_signals
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
    spec_l = get_strategy("impulse_1m_long")
    assert spec_l.name == "impulse_1m_long"
    assert spec_l.role == "uptrend"

    spec_s = get_strategy("impulse_1m_short")
    assert spec_s.name == "impulse_1m_short"
    assert spec_s.role == "downtrend"
