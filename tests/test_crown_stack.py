"""Crown stack indicators + signals (shipped strategy path)."""

from __future__ import annotations

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.crown_stack import crown_stack_long, register_crown_stack
from hypervector.strategies.indicators import bbwp, ema, ema_bias, pmarp, rsi
from hypervector.strategies.registry import clear_registry, get_strategy
from hypervector.sweep.search import run_grid_search


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


def test_crown_stack_long_returns_bool_series():
    df = fixture_ohlcv(n_bars=60 * 24 * 50, drift=8.0, wave_period=120)
    entries, exits, direction = crown_stack_long(
        df, bbwp_lookback=50, pmarp_lookback=50
    )
    assert direction == "long"
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert len(entries) == len(df)


def test_crown_stack_grid_runs():
    clear_registry()
    register_crown_stack()
    df = fixture_ohlcv(n_bars=60 * 24 * 45, drift=10.0, wave_period=100)
    strat = get_strategy("crown_stack_long")
    results = run_grid_search(
        df,
        strat,
        param_grid={
            "bbwp_lookback": [50],
            "bbwp_threshold": [25.0],
            "pmarp_exit_hi": [90.0],
        },
    )
    assert results
    assert results[0].status in ("ok", "error")
    ok = [r for r in results if r.status == "ok"]
    assert ok
    assert "net_pnl" in ok[0].metrics
    clear_registry()
