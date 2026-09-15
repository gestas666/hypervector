"""Regression for a recipe exit flipped by pre-window floating-point history."""

import numpy as np
import pandas as pd

from hypervector.research.hourly_band_reentry import build_hourly_band_reentry_signals


def test_identical_twenty_hour_window_keeps_exact_band_and_exit_values() -> None:
    """A historical SPCX equality case must not depend on discarded older closes."""
    tail = [
        111.38,
        111.36,
        111.46,
        111.76,
        111.84,
        111.66,
        111.81,
        111.59,
        111.64,
        111.71,
        111.76,
        111.85,
        111.76,
        111.95,
        112.15,
        111.98,
        111.90,
        112.19,
        111.69,
        111.76,
    ]
    bars = _quarter_hour_bars([100.01] * 180 + tail)
    full = build_hourly_band_reentry_signals(bars).iloc[-1]
    restarted = build_hourly_band_reentry_signals(bars.iloc[-333:]).iloc[-1]
    for field in ("band_mean", "band_lower", "band_upper", "long_exit", "short_exit"):
        assert full[field] == restarted[field], field
    assert full.band_mean == np.mean(np.array(tail, dtype=np.float64))


def test_population_deviation_ignores_discarded_history() -> None:
    """Stable means alone must not hide accumulation errors in population bands."""
    closes = [100.0 + (position % 7) * 0.01 for position in range(200)]
    bars = _quarter_hour_bars(closes)
    full = build_hourly_band_reentry_signals(bars).iloc[-1]
    restarted = build_hourly_band_reentry_signals(bars.iloc[-333:]).iloc[-1]
    mean, deviation = np.mean(closes[-20:]), np.std(closes[-20:], ddof=0)
    assert full.band_mean == restarted.band_mean
    assert full.band_lower == restarted.band_lower == mean - 2.0 * deviation
    assert full.band_upper == restarted.band_upper == mean + 2.0 * deviation


def _quarter_hour_bars(closes: list[float]) -> pd.DataFrame:
    """Expand a deterministic hourly fixture into complete quarter-hour candles."""
    close = np.repeat(closes, 4)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 10.0,
        },
        index=pd.date_range("2026-01-01", periods=len(close), freq="15min", tz="UTC"),
    )
