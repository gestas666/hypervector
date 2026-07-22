"""Regime + uptrend + downtrend offline tracks (SRS_HV1_START_THREE)."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.data.sources import fixture_ohlcv
from hypervector.regime.detectors import REGIME_LABELS, detect_regime_ema
from hypervector.regime.metrics import regime_detection_metrics
from hypervector.strategies.classic import register_classic_baselines
from hypervector.strategies.registry import clear_registry, get_strategy, list_strategies
from hypervector.sweep.metrics import REQUIRED_METRIC_KEYS, compute_trial_metrics
from hypervector.sweep.search import run_grid_search


@pytest.fixture(autouse=True)
def _fresh_registry():
    clear_registry()
    register_classic_baselines()
    yield
    clear_registry()


def test_regime_labels_only_up_down_range():
    # Strong uptrend then flat
    up = fixture_ohlcv(n_bars=200, drift=15.0, source="fixture")
    labels = detect_regime_ema(up["close"], fast=5, slow=20, range_band=0.0005)
    assert set(labels.unique()).issubset(REGIME_LABELS)
    assert (labels == "up").sum() > 0
    metrics = regime_detection_metrics(labels)
    assert metrics["n_bars"] == 200
    assert 0.0 <= metrics["pct_up"] <= 1.0
    assert abs(metrics["pct_up"] + metrics["pct_down"] + metrics["pct_range"] - 1.0) < 1e-9


def test_regime_downtrend_detects_down():
    down = fixture_ohlcv(n_bars=200, drift=-15.0, source="fixture")
    labels = detect_regime_ema(down["close"], fast=5, slow=20, range_band=0.0005)
    assert (labels == "down").sum() > 0
    assert set(labels.unique()).issubset(REGIME_LABELS)


def test_uptrend_search_ranks_by_net_pnl():
    df = fixture_ohlcv(n_bars=400, drift=25.0, source="fixture", wave_period=30)
    strat = get_strategy("ma_cross_long")
    assert strat.role == "uptrend"
    results = run_grid_search(
        df,
        strat,
        param_grid={"fast": [5, 8], "slow": [20, 40]},
    )
    ok = [r for r in results if r.status == "ok"]
    assert len(ok) >= 1
    # Sorted descending by net_pnl
    pnls = [r.net_pnl for r in ok]
    assert pnls == sorted(pnls, reverse=True)
    for key in REQUIRED_METRIC_KEYS:
        assert key in ok[0].metrics
    # Wavy fixture must produce at least one trade on some trial
    assert any(r.metrics.get("trade_count", 0) > 0 for r in ok)
    # No risk-gate rejections — only ok or error
    assert all(r.status in ("ok", "error") for r in results)


def test_downtrend_search_produces_ranked_metrics():
    df = fixture_ohlcv(n_bars=400, drift=-25.0, source="fixture", wave_period=30)
    strat = get_strategy("ma_cross_short")
    assert strat.role == "downtrend"
    results = run_grid_search(
        df,
        strat,
        param_grid={"fast": [5, 10], "slow": [20, 30]},
    )
    ok = [r for r in results if r.status == "ok"]
    assert len(ok) >= 1
    for r in ok:
        for key in REQUIRED_METRIC_KEYS:
            assert key in r.metrics
    assert any(r.metrics.get("trade_count", 0) > 0 for r in ok)
    pnls = [r.net_pnl for r in ok]
    assert pnls == sorted(pnls, reverse=True)


def test_compute_trial_metrics_drives_vectorbt():
    df = fixture_ohlcv(n_bars=100, drift=5.0)
    entries = pd.Series(False, index=df.index)
    exits = pd.Series(False, index=df.index)
    entries.iloc[10] = True
    exits.iloc[50] = True
    m = compute_trial_metrics(df["close"], entries, exits, direction="long")
    for key in REQUIRED_METRIC_KEYS:
        assert key in m
    assert isinstance(m["net_pnl"], float)
    assert isinstance(m["trade_count"], int)


def test_technical_failure_does_not_abort_other_trials():
    df = fixture_ohlcv(n_bars=100, drift=1.0)
    strat = get_strategy("ma_cross_long")

    def flaky(df, fast=5, slow=20):
        if fast == 5:
            raise RuntimeError("simulated technical failure")
        return strat.build_signals(df, fast=fast, slow=slow)

    from hypervector.strategies.registry import StrategySpec

    bad = StrategySpec(
        name="flaky",
        role="uptrend",
        param_grid={"fast": [5, 8], "slow": [20]},
        build_signals=flaky,
    )
    results = run_grid_search(df, bad)
    assert any(r.status == "error" for r in results)
    assert any(r.status == "ok" for r in results)


def test_list_strategies_by_role():
    assert len(list_strategies(role="uptrend")) >= 1
    assert len(list_strategies(role="downtrend")) >= 1
