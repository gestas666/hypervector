"""Tests for advanced book_flow, adaptive regime, ensemble, and portfolio modules."""

import numpy as np
import pandas as pd

from hypervector.data.book_flow import compute_advanced_book_features
from hypervector.ml.ensemble import EnsembleMetalabeler
from hypervector.regime.adaptive import detect_4state_regime
from hypervector.sweep.portfolio import run_long_short_portfolio


def _make_dummy_df(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    close = 60000.0 + np.cumsum(np.random.randn(n) * 50.0)
    high = close + np.random.rand(n) * 20.0
    low = close - np.random.rand(n) * 20.0
    open_ = close + np.random.randn(n) * 5.0
    volume = 10.0 + np.random.rand(n) * 5.0
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=ts,
    )


def test_book_flow():
    df_book = pd.DataFrame(
        {
            "micro_price": [64790.0, 64792.0, 64795.0],
            "mid": [64790.0, 64791.0, 64793.0],
            "bid_depth_10": [10.0, 15.0, 8.0],
            "ask_depth_10": [5.0, 5.0, 12.0],
            "spread_bps": [1.5, 2.0, 1.8],
        }
    )
    res = compute_advanced_book_features(df_book)
    assert "micro_price_velocity_1s" in res.columns
    assert "order_pressure_index" in res.columns
    assert "spread_regime_limit" in res.columns


def test_adaptive_4state_regime():
    df = _make_dummy_df(150)
    regimes = detect_4state_regime(df)
    assert len(regimes) == len(df)
    assert set(regimes.unique()).issubset(
        {"BULL_TREND", "BEAR_TREND", "HIGH_VOL_COMPRESSION", "LOW_VOL_CHOP"}
    )


def test_ensemble_metalabeler():
    np.random.seed(42)
    n = 100
    X = pd.DataFrame(
        {
            "close_vs_ema21_bps": np.random.randn(n) * 10.0,
            "rsi_1m": np.random.uniform(30, 70, n),
            "adx_1m": np.random.uniform(10, 40, n),
        }
    )
    y = np.random.choice([0, 1], size=n)
    ml = EnsembleMetalabeler(feature_names=list(X.columns))
    ml.fit(X, y)

    prob = ml.predict_probability(X.iloc[0].to_dict())
    assert 0.0 <= prob <= 1.0

    mult = ml.compute_conviction_size_multiplier(X.iloc[0].to_dict())
    assert mult >= 0.0


def test_portfolio_allocator():
    df = _make_dummy_df(150)
    res = run_long_short_portfolio(
        df,
        long_strategy_name="pine_composite_long",
        short_strategy_name="pine_composite_short",
    )
    assert "net_pnl" in res.combined_metrics
    assert "sharpe" in res.combined_metrics
