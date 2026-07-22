"""Trend-ride frankenstein strategy tests."""

from __future__ import annotations

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.indicators import (
    choppiness_index,
    squeeze_momentum,
    supertrend,
    vortex,
)
from hypervector.strategies.registry import clear_registry, get_strategy
from hypervector.strategies.trend_ride import register_trend_ride, trend_ride_long
from hypervector.sweep.search import run_grid_search


def test_supertrend_chops_vortex_shapes():
    df = fixture_ohlcv(n_bars=500, drift=3.0, wave_period=50)
    st, d = supertrend(df["high"], df["low"], df["close"], atr_period=10, multiplier=3.0)
    assert len(st) == len(df)
    assert set(d.unique()).issubset({-1, 0, 1})
    chop = choppiness_index(df["high"], df["low"], df["close"], 14)
    assert chop.notna().sum() > 50
    vip, vim = vortex(df["high"], df["low"], df["close"], 14)
    assert vip.notna().sum() > 50
    mom, on, off = squeeze_momentum(df["high"], df["low"], df["close"])
    assert len(mom) == len(df)


def test_trend_ride_signals_and_grid():
    clear_registry()
    register_trend_ride()
    df = fixture_ohlcv(n_bars=2000, drift=8.0, wave_period=80)
    e, x, d = trend_ride_long(df, st_mult=3.0, chop_max=55.0, use_squeeze=False)
    assert d == "long"
    assert e.dtype == bool
    strat = get_strategy("trend_ride_long")
    results = run_grid_search(
        df,
        strat,
        param_grid={"st_mult": [3.0], "chop_max": [55.0], "use_squeeze": [False]},
    )
    ok = [r for r in results if r.status == "ok"]
    assert ok
    assert "net_pnl" in ok[0].metrics
    clear_registry()
