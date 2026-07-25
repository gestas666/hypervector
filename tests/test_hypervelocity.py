"""Hypervelocity reverse-engineered scalper signals (docs/external plan)."""

from __future__ import annotations

import pandas as pd

from hypervector.data.sources import fixture_ohlcv
from hypervector.strategies.hypervelocity import (
    build_hypervelocity_signals,
    hypervelocity_long,
    hypervelocity_short,
    register_hypervelocity,
)
from hypervector.strategies.indicators import ema
from hypervector.strategies.registry import clear_registry, get_strategy
from hypervector.sweep.search import run_grid_search


def test_hypervelocity_long_returns_bool_series():
    df = fixture_ohlcv(n_bars=3000, drift=8.0, wave_period=120)
    entries, exits, direction = hypervelocity_long(df)
    assert direction == "long"
    assert entries.dtype == bool
    assert exits.dtype == bool
    assert len(entries) == len(df)
    assert not (entries & exits).any()


def test_hypervelocity_short_mirrors_long():
    df = fixture_ohlcv(n_bars=3000, drift=-8.0, wave_period=120)
    entries, exits, direction = hypervelocity_short(df)
    assert direction == "short"
    assert entries.dtype == bool
    assert len(exits) == len(df)


def test_long_entries_only_with_trend_alignment():
    """Plan section 3.1: no counter-trend trades — entries align with EMA trend."""
    df = fixture_ohlcv(n_bars=4000, drift=6.0, wave_period=90)
    entries, _, _ = hypervelocity_long(df, regime_filter=False)
    close = df["close"].astype(float)
    trend_up = ema(close, 9) > ema(close, 21)
    assert entries.sum() > 0
    assert bool((entries & ~trend_up).sum() == 0)


def test_target_margin_maps_to_price_move():
    """8% margin at 40x == 0.2% price target; barrier exit must fire after entry."""
    df = fixture_ohlcv(n_bars=4000, drift=10.0, wave_period=80)
    entries, exits, _ = build_hypervelocity_signals(
        df, direction="long", target_margin_pct=8.0, leverage=40.0, regime_filter=False
    )
    assert entries.sum() > 0
    assert exits.sum() > 0
    first_entry = entries.idxmax()
    assert exits.loc[first_entry:].sum() > 0


def test_hypervelocity_grid_runs():
    clear_registry()
    register_hypervelocity()
    df = fixture_ohlcv(n_bars=6000, drift=10.0, wave_period=100)
    strat = get_strategy("hypervelocity_1m_scalper_long")
    results = run_grid_search(
        df,
        strat,
        param_grid={
            "target_margin_pct": [8.0],
            "leverage": [40.0],
            "atr_stop_mult": [1.5],
            "momentum_lookback": [3],
            "regime_filter": [False],
        },
    )
    assert results
    ok = [r for r in results if r.status == "ok"]
    assert ok
    assert "net_pnl" in ok[0].metrics
    clear_registry()
