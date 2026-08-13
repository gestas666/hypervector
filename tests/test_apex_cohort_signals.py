"""Causal signal contracts for repaired Apex-derived candidates."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.apex_cohort_signals import (
    MeanReversionConfig,
    OITrendConfig,
    build_apex_mean_reversion_v2,
    build_apex_oi_trend_v2,
)


def _bars(
    close: np.ndarray,
    *,
    volume: np.ndarray | None = None,
) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close), freq="5min", tz="UTC")
    observed_volume = volume if volume is not None else np.full(len(close), 100.0)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": observed_volume,
        },
        index=index,
    )


def _books(index: pd.DatetimeIndex, pressure: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "imbalance_5_delta_60s": pressure,
            "micro_price_delta_bps": pressure,
        },
        index=index,
    )


def _contexts(index: pd.DatetimeIndex, oi: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_interest": oi,
            "available_at": index + pd.Timedelta(minutes=5),
        },
        index=index,
    )


def test_mean_reversion_emits_one_fresh_long_exhaustion_episode() -> None:
    close = np.concatenate((np.full(20, 100.0), np.array([90.0, 89.0])))
    bars = _bars(close)
    pressure = np.concatenate((np.zeros(20), np.array([0.2, 0.2])))

    signals = build_apex_mean_reversion_v2(
        bars,
        _books(bars.index, pressure),
        MeanReversionConfig(lookback=20, entry_z=2.0, pressure_threshold=0.1),
    )

    assert signals["long_entry"].sum() == 1
    assert signals["long_entry"].iloc[-2]
    assert not signals["long_entry"].iloc[-1]
    assert signals["zscore"].iloc[-2] < -2.0


def test_mean_reversion_requires_opposing_exhaustion_pressure() -> None:
    bars = _bars(np.concatenate((np.full(20, 100.0), np.array([90.0]))))

    signals = build_apex_mean_reversion_v2(
        bars,
        _books(bars.index, np.zeros(len(bars))),
        MeanReversionConfig(lookback=20, entry_z=2.0, pressure_threshold=0.1),
    )

    assert not signals[["long_entry", "short_entry"]].to_numpy().any()


def test_mean_reversion_exposes_mean_cross_and_invalidation_exits() -> None:
    close = np.concatenate((np.full(20, 100.0), np.array([90.0, 100.0, 80.0])))
    bars = _bars(close)
    pressure = np.concatenate((np.zeros(20), np.array([0.2, 0.0, 0.2])))

    signals = build_apex_mean_reversion_v2(
        bars,
        _books(bars.index, pressure),
        MeanReversionConfig(
            lookback=20,
            entry_z=2.0,
            exit_z=0.5,
            invalidation_z=3.0,
            pressure_threshold=0.1,
        ),
    )

    assert signals["long_exit_mean"].iloc[-2]
    assert signals["long_exit_invalidation"].iloc[-1]


def test_oi_trend_uses_true_interval_volume_and_fresh_context() -> None:
    close = np.array([100.0, 100.2, 100.4, 100.6, 101.2])
    volume = np.array([100.0, 100.0, 100.0, 100.0, 200.0])
    bars = _bars(close, volume=volume)
    contexts = _contexts(bars.index, np.array([100.0, 100.1, 100.2, 100.4, 101.0]))

    signals = build_apex_oi_trend_v2(
        bars,
        contexts,
        OITrendConfig(
            lookback=3,
            volume_lookback=3,
            price_change_bps=20.0,
            oi_change_bps=20.0,
            volume_surge_mult=1.5,
        ),
    )

    assert signals["long_entry"].iloc[-1]
    assert signals["volume_surge"].iloc[-1]
    assert signals["oi_eligible"].iloc[-1]


def test_oi_trend_rejects_repeated_rolling_volume_and_stale_oi() -> None:
    close = np.array([100.0, 100.2, 100.4, 100.6, 101.2])
    bars = _bars(close, volume=np.full(len(close), 100.0))
    contexts = _contexts(bars.index, np.array([100.0, 100.1, 100.2, 100.4, 101.0]))
    config = OITrendConfig(
        lookback=3,
        volume_lookback=3,
        price_change_bps=20.0,
        oi_change_bps=20.0,
        volume_surge_mult=1.5,
    )

    flat_volume = build_apex_oi_trend_v2(bars, contexts, config)
    stale_contexts = contexts.copy()
    stale_contexts.loc[stale_contexts.index[-1], "available_at"] -= pd.Timedelta(
        minutes=10
    )
    stale = build_apex_oi_trend_v2(
        _bars(close, volume=np.array([100.0, 100.0, 100.0, 100.0, 200.0])),
        stale_contexts,
        config,
    )

    assert not flat_volume[["long_entry", "short_entry"]].to_numpy().any()
    assert not stale["oi_eligible"].iloc[-1]
    assert not stale[["long_entry", "short_entry"]].iloc[-1].any()


def test_oi_trend_exposes_divergence_exit() -> None:
    close = np.array([100.0, 100.2, 100.4, 100.6, 101.2, 101.3])
    volume = np.array([100.0, 100.0, 100.0, 100.0, 200.0, 100.0])
    bars = _bars(close, volume=volume)
    contexts = _contexts(
        bars.index,
        np.array([100.0, 100.1, 100.2, 100.4, 101.0, 99.0]),
    )

    signals = build_apex_oi_trend_v2(
        bars,
        contexts,
        OITrendConfig(
            lookback=3,
            volume_lookback=3,
            price_change_bps=20.0,
            oi_change_bps=20.0,
            volume_surge_mult=1.5,
        ),
    )

    assert signals["long_exit_divergence"].iloc[-1]
