"""RSI, BBWP, PMARP and EMA-bias indicator basics."""

from __future__ import annotations

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.indicators import bbwp, ema, ema_bias, pmarp, rsi


def test_rsi_bbwp_pmarp_shapes():
    df = fixture_ohlcv(n_bars=400, drift=5.0, wave_period=40)
    close = df["close"]
    r = rsi(close, 14)
    assert len(r) == len(close)
    assert r.between(0, 100).all()
    pct, sig = bbwp(close, lookback=100, signal_sma=5)
    assert pct.notna().sum() > 50
    pm = pmarp(close, lookback=100, ema_length=21)
    assert pm.notna().sum() > 50


def test_ema_bias_is_chart_tf_not_daily_resample():
    """21/55 bias uses bar-count EMAs on the series (1m), not calendar days."""
    df = fixture_ohlcv(n_bars=300, drift=5.0, wave_period=60)
    close = df["close"]
    bias = ema_bias(close, fast=21, slow=55)
    assert len(bias) == len(df)
    assert set(bias.unique()).issubset({-1, 0, 1})
    # Must match direct 1m EMA compare (proves no daily resample)
    f = ema(close, 21)
    s = ema(close, 55)
    expected = pd.Series(0, index=close.index, dtype=int)
    expected = expected.mask(f > s, 1).mask(f < s, -1).fillna(0).astype(int)
    pd.testing.assert_series_equal(bias, expected, check_names=False)
