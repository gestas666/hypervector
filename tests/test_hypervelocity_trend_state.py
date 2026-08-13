"""Causal tests for the price-only DAFE Trend State research port."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.hypervelocity_trend_state import (
    PriceTrendStateConfig,
    classify_price_trend_state,
)


def _bars(close: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close), freq="1min", tz="UTC")
    values = np.asarray(close, dtype=float)
    prior = np.r_[values[0], values[:-1]]
    return pd.DataFrame(
        {
            "open": prior,
            "high": np.maximum(prior, values) + 0.25,
            "low": np.minimum(prior, values) - 0.25,
            "close": values,
            "volume": np.full(len(values), 10.0),
        },
        index=index,
    )


def test_trend_state_rejects_invalid_ohlcv() -> None:
    bars = _bars([100.0, 101.0]).drop(columns="volume")
    with pytest.raises(ValueError, match="missing columns"):
        classify_price_trend_state(bars)


def test_trend_state_is_prefix_invariant() -> None:
    values = [100.0] * 20 + list(np.linspace(100.0, 120.0, 80))
    bars = _bars(values)
    full = classify_price_trend_state(bars)
    prefix = classify_price_trend_state(bars.iloc[:63])
    pd.testing.assert_frame_equal(full.iloc[:63], prefix)


def test_trend_state_detects_bull_and_bear_control() -> None:
    values = [100.0] * 30
    values += list(np.linspace(100.0, 130.0, 90))
    values += list(np.linspace(130.0, 80.0, 120))
    result = classify_price_trend_state(_bars(values))
    assert "BULL" in result["trend_state"].iloc[30:120].to_list()
    assert result["trend_state"].iloc[-1] == "BEAR"
    assert result["bear_shift"].sum() >= 1


def test_trend_state_config_validates_decay() -> None:
    with pytest.raises(ValueError, match="decay_rate"):
        PriceTrendStateConfig(decay_rate=1.0)
