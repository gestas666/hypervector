"""Tests for pine_composite strategy module."""

import numpy as np
import pandas as pd

from hypervector.strategies.pine_composite import (
    pine_composite_long,
    pine_composite_short,
)


def _make_dummy_ohlcv(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    close = 60000.0 + np.cumsum(np.random.randn(n) * 50.0)
    high = close + np.random.rand(n) * 20.0
    low = close - np.random.rand(n) * 20.0
    open_ = close + np.random.randn(n) * 5.0
    volume = 10.0 + np.random.rand(n) * 5.0
    ts = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=ts,
    )


def test_pine_composite_long_short_signals():
    df = _make_dummy_ohlcv(150)
    entries_l, exits_l, dir_l = pine_composite_long(df)
    assert dir_l == "long"
    assert len(entries_l) == len(df)
    assert len(exits_l) == len(df)
    assert not (entries_l & exits_l).any()

    entries_s, exits_s, dir_s = pine_composite_short(df)
    assert dir_s == "short"
    assert len(entries_s) == len(df)
    assert len(exits_s) == len(df)
    assert not (entries_s & exits_s).any()
