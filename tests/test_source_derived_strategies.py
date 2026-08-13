"""Tests for source-derived, causal BTC strategy hypotheses."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.strategies.registry import SignalBuilder
from hypervector.strategies.source_derived import (
    donchian_trend_signals,
    liquidity_sweep_signals,
    source_derived_builders,
)


def test_donchian_long_uses_only_prior_range() -> None:
    bars = _flat_bars(40)
    bars.iloc[-1, bars.columns.get_loc("close")] = 102.0
    bars.iloc[-1, bars.columns.get_loc("high")] = 102.5

    entries, exits, direction = donchian_trend_signals(
        bars,
        direction="long",
        entry_lookback=20,
        exit_lookback=10,
        ema_length=5,
    )

    assert direction == "long"
    assert entries.iloc[-1]
    assert not exits.iloc[-1]
    assert entries.iloc[:-1].sum() == 0


def test_liquidity_sweep_long_requires_wick_below_and_close_reclaim() -> None:
    bars = _flat_bars(40)
    bars.iloc[-1, bars.columns.get_loc("low")] = 98.0
    bars.iloc[-1, bars.columns.get_loc("close")] = 100.25
    bars.iloc[-1, bars.columns.get_loc("volume")] = 2.0

    entries, _, direction = liquidity_sweep_signals(
        bars,
        direction="long",
        lookback=20,
        volume_multiple=1.2,
        ema_length=5,
    )

    assert direction == "long"
    assert entries.iloc[-1]


def test_source_cohort_contains_four_pairs_plus_regime_router_pair() -> None:
    assert len(source_derived_builders()) == 10


@pytest.mark.parametrize("builder", source_derived_builders())
def test_source_derived_strategy_does_not_rewrite_past_signals(
    builder: SignalBuilder,
) -> None:
    bars = _random_bars(500)
    prefix = bars.iloc[:-1]

    prefix_entry, prefix_exit, _ = builder(prefix)
    full_entry, full_exit, _ = builder(bars)

    pd.testing.assert_series_equal(prefix_entry, full_entry.iloc[:-1])
    pd.testing.assert_series_equal(prefix_exit, full_exit.iloc[:-1])


def _flat_bars(periods: int) -> pd.DataFrame:
    """Return deterministic flat OHLCV bars for trigger tests."""
    index = pd.date_range("2026-01-01", periods=periods, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 1.0,
        },
        index=index,
    )


def _random_bars(periods: int) -> pd.DataFrame:
    """Return deterministic non-degenerate OHLCV bars for causality checks."""
    rng = np.random.default_rng(20260729)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.002, periods)))
    spread = rng.uniform(0.0005, 0.003, periods)
    open_price = np.r_[close[0], close[:-1]]
    index = pd.date_range("2026-01-01", periods=periods, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": open_price,
            "high": np.maximum(open_price, close) * (1.0 + spread),
            "low": np.minimum(open_price, close) * (1.0 - spread),
            "close": close,
            "volume": rng.lognormal(0.0, 0.5, periods),
        },
        index=index,
    )
