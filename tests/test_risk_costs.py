"""Costs, TP/SL modes, conviction sizing — real compute_trial_metrics path."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.sweep.costs import CostModel, resolve_cost_model
from hypervector.sweep.exits import ExitConfig, stop_distance_frac
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import (
    RiskConfig,
    risk_pct_from_conviction,
    size_frac_from_risk,
)


def test_conviction_maps_1_to_5_pct():
    cfg = RiskConfig(risk_pct_min=0.01, risk_pct_max=0.05)
    assert risk_pct_from_conviction(0.0, cfg) == pytest.approx(0.01)
    assert risk_pct_from_conviction(1.0, cfg) == pytest.approx(0.05)
    assert risk_pct_from_conviction(0.5, cfg) == pytest.approx(0.03)


def test_size_frac_scales_with_stop():
    cfg = RiskConfig()
    idx = pd.RangeIndex(5)
    stop = pd.Series([0.01, 0.02, 0.01, 0.05, 0.01], index=idx)
    size = size_frac_from_risk(0.02, stop, cfg)  # 2% risk
    # 0.02/0.01 → 2.0 notional fraction but capped at max_size_frac=1.0
    assert size.iloc[0] == pytest.approx(1.0)
    assert size.iloc[1] == pytest.approx(1.0)  # 0.02/0.02 = 1.0
    # tighter stop with higher max allows uncapped ratio
    cfg2 = RiskConfig(max_size_frac=5.0)
    size2 = size_frac_from_risk(0.02, stop, cfg2)
    assert size2.iloc[0] == pytest.approx(2.0)


def test_three_exit_modes_produce_stops():
    df = fixture_ohlcv(n_bars=200, drift=2.0, wave_period=40)
    for mode in ("fixed_rr", "atr", "trail"):
        cfg = ExitConfig(mode=mode)  # type: ignore[arg-type]
        s = stop_distance_frac(df, cfg)
        assert s.notna().sum() > 50
        assert (s > 0).all()


def test_metrics_with_costs_and_atr_tp_sl():
    df = fixture_ohlcv(n_bars=300, drift=5.0, wave_period=30)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[40] = True
    exits.iloc[120] = True
    m = compute_trial_metrics(
        df["close"],
        entries,
        exits,
        direction="long",
        init_cash=10_000.0,
        df=df,
        cost=CostModel(taker_fee=0.00035, slippage_bps=2.0, funding_rate_8h=0.0001),
        exit_cfg=ExitConfig(mode="atr", sl_atr_mult=1.5, rr=2.0),
        risk_cfg=RiskConfig(default_conviction=0.8),  # high conviction → ~4.2% risk
        conviction=0.8,
        apply_costs=True,
    )
    for k in (
        "net_pnl",
        "total_return_pct",
        "trade_count",
        "funding_cost",
        "avg_risk_pct",
        "exit_mode",
        "slippage_bps",
    ):
        assert k in m
    assert m["exit_mode"] == "atr"
    assert m["init_cash"] == 10_000.0
    assert m["avg_risk_pct"] == pytest.approx(4.2, rel=0.05)
    assert m["slippage_bps"] == 2.0


def test_resolve_cost_presets():
    assert resolve_cost_model("zero").taker_fee == 0.0
    assert resolve_cost_model("hl_taker_default").taker_fee > 0
