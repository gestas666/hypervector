"""Contracts for causal bar translations of the Apex directional entries."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.apex_directional_signals import (
    build_apex_breakout_entries,
    build_apex_ensemble_entries,
    build_apex_trend_entries,
)


def _bars(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close), freq="5min", tz="UTC")
    volumes = volume if volume is not None else np.full(len(close), 100.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": volumes,
        },
        index=index,
    )


def test_trend_entries_require_a_fresh_ema_cross() -> None:
    close = np.concatenate((np.linspace(110.0, 90.0, 50), np.linspace(90.0, 120.0, 50)))

    signals = build_apex_trend_entries(_bars(close), adx_threshold=0.0)

    assert signals.index.equals(_bars(close).index)
    assert signals["long_entry"].sum() == 1
    assert signals["short_entry"].sum() == 0
    cross_at = signals.index[signals["long_entry"]][0]
    assert signals.loc[cross_at, "ema_fast"] > signals.loc[cross_at, "ema_slow"]


def test_trend_threshold_can_reject_the_same_cross() -> None:
    close = np.concatenate((np.linspace(110.0, 90.0, 50), np.linspace(90.0, 120.0, 50)))

    signals = build_apex_trend_entries(_bars(close), adx_threshold=101.0)

    assert not signals[["long_entry", "short_entry"]].to_numpy().any()


def test_ensemble_uses_four_directional_votes_not_bb_as_a_vote() -> None:
    close = np.linspace(100.0, 180.0, 100)

    signals = build_apex_ensemble_entries(_bars(close))

    assert signals.attrs["min_votes"] == 4
    assert signals["long_entry"].sum() == 1
    entry = signals.loc[signals["long_entry"]].iloc[0]
    assert entry["bull_votes"] >= 4
    assert "bb_compressed" in signals.columns
    assert not signals["short_entry"].any()


def test_ensemble_flat_compression_does_not_create_direction() -> None:
    signals = build_apex_ensemble_entries(_bars(np.full(100, 100.0)))

    assert signals["bb_compressed"].iloc[-1]
    assert signals["bull_votes"].max() == 0
    assert signals["bear_votes"].max() == 0
    assert not signals[["long_entry", "short_entry"]].to_numpy().any()


def test_breakout_uses_prior_range_and_prior_bar_volume_average() -> None:
    close = np.concatenate((np.full(20, 100.0), np.array([102.0])))
    volume = np.concatenate((np.full(20, 100.0), np.array([201.0])))
    bars = _bars(close, volume)
    bars.iloc[-1, bars.columns.get_loc("high")] = 103.0

    signals = build_apex_breakout_entries(bars)

    assert signals["long_entry"].iloc[-1]
    assert signals["prior_high"].iloc[-1] == pytest.approx(100.2)
    assert signals["prior_volume_mean"].iloc[-1] == pytest.approx(100.0)
    assert not signals["short_entry"].iloc[-1]


def test_builders_reject_unordered_or_malformed_bars() -> None:
    bars = _bars(np.linspace(100.0, 110.0, 50))
    unordered = bars.iloc[::-1]
    malformed = bars.drop(columns="volume")

    with pytest.raises(ValueError, match="ordered"):
        build_apex_trend_entries(unordered)
    with pytest.raises(ValueError, match="missing"):
        build_apex_breakout_entries(malformed)
