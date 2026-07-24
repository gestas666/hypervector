"""Unit test for ultimate 5-tier regime engine."""

import numpy as np
import pandas as pd
import pytest

from hypervector.regime.ultimate import detect_ultimate_regime


def _make_dummy_df(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    close = 60000.0 + np.cumsum(np.random.randn(n) * 50.0)
    high = close + np.random.rand(n) * 20.0
    low = close - np.random.rand(n) * 20.0
    open_ = close + np.random.randn(n) * 5.0
    volume = 10.0 + np.random.rand(n) * 5.0
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "spread_bps": 2.0, "obi_5": 0.1},
        index=ts,
    )


def test_ultimate_regime():
    df_1m = _make_dummy_df(150)
    res = detect_ultimate_regime(df_1m)
    assert "regime_state" in res.columns
    assert "long_weight" in res.columns
    assert "short_weight" in res.columns
    assert len(res) == len(df_1m)
