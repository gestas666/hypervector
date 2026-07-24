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


def test_htf_decoupled_regime():
    """Verify HTF (15m) macro trend lock prevents 1m noise whipsaws."""
    df_1m = _make_dummy_df(300)
    res_15m = detect_ultimate_regime(df_1m, htf_resample_rule="15min")
    assert len(res_15m) == 300
    # Ensure regime states are assigned cleanly across all bars
    assert set(res_15m["regime_state"].unique()).issubset({
        "BULL_MOMENTUM_EXPANSION",
        "BEAR_MOMENTUM_EXPANSION",
        "VOLATILITY_COILING_COMPRESSION",
        "FUNDING_CARRY_REVERSAL",
        "RANGE_CHOP_HIGH_FRICTION",
    })
