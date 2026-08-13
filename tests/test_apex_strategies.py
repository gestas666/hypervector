"""Unit tests for ported Apex strategies (oi_divergence & funding_momentum)."""

import numpy as np
import pandas as pd

from hypervector.strategies import get_strategy, register_all_strategies


def _make_dummy_df(n: int = 150) -> pd.DataFrame:
    np.random.seed(42)
    close = 60000.0 + np.cumsum(np.random.randn(n) * 50.0)
    high = close + np.random.rand(n) * 20.0
    low = close - np.random.rand(n) * 20.0
    open_ = close + np.random.randn(n) * 5.0
    volume = 10.0 + np.random.rand(n) * 5.0
    oi = 100.0 + np.cumsum(np.random.randn(n) * 2.0)
    fr = np.random.randn(n) * 0.0001
    ts = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "open_interest": oi,
            "funding_rate": fr,
        },
        index=ts,
    )


def test_oi_divergence_strategy():
    register_all_strategies()
    df = _make_dummy_df(150)

    strat_long = get_strategy("oi_divergence_long")
    entries_l, exits_l, dir_l = strat_long.build_signals(df)
    assert dir_l == "long"
    assert len(entries_l) == len(df)

    strat_short = get_strategy("oi_divergence_short")
    entries_s, exits_s, dir_s = strat_short.build_signals(df)
    assert dir_s == "short"
    assert len(entries_s) == len(df)


def test_funding_momentum_strategy():
    register_all_strategies()
    df = _make_dummy_df(150)

    strat_long = get_strategy("funding_momentum_long")
    entries_l, exits_l, dir_l = strat_long.build_signals(df)
    assert dir_l == "long"
    assert len(entries_l) == len(df)

    strat_short = get_strategy("funding_momentum_short")
    entries_s, exits_s, dir_s = strat_short.build_signals(df)
    assert dir_s == "short"
    assert len(entries_s) == len(df)
