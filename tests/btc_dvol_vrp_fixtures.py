"""Deterministic BTC DVOL-VRP research fixtures."""

from __future__ import annotations

import numpy as np
import pandas as pd


_SIGNAL = pd.Timestamp("2026-08-03T12:00:00Z")


def dvol_vrp_market(hours: int) -> pd.DataFrame:
    """Return uninterrupted flat BTC minutes with exact zero funding."""
    index = pd.date_range("2026-08-01", periods=hours * 60, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.05,
            "low": 99.95,
            "close": 100.0,
            "volume": 1.0,
            "funding_rate": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )


def dvol_vrp_features() -> pd.DataFrame:
    """Return one qualifying primary onset and no strategic exit."""
    source = pd.date_range(
        _SIGNAL - pd.Timedelta(hours=4),
        periods=8,
        freq="h",
    )
    decision = source + pd.Timedelta(hours=1)
    qualifying = decision == _SIGNAL
    return pd.DataFrame(
        {
            "source_timestamp": source,
            "decision_time": decision,
            "btc_close": 101.0,
            "ema24": 100.0,
            "vrp": 0.3,
            "vrp_median": 0.2,
            "high_vrp": qualifying,
            "low_vrp": False,
            "bullish_structure": qualifying,
        }
    )


def dvol_vrp_dvol(bars: pd.DataFrame) -> pd.DataFrame:
    """Return aligned positive hourly DVOL evidence for minute bars."""
    timestamps = bars.resample("1h").first().index
    rows = len(timestamps)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": np.full(rows, 60.0),
            "high": np.full(rows, 61.0),
            "low": np.full(rows, 59.0),
            "close": np.full(rows, 60.0),
        }
    )
