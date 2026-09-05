"""Deterministic fixtures for BTC spot-lead catch-up research."""

from __future__ import annotations

import numpy as np
import pandas as pd


def spot_lead_signal_bars() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
]:
    """Return completed-minute inputs with one event for each frozen arm."""
    start = pd.Timestamp("2025-08-01T00:00:00Z")
    minutes = 64 * 60
    index = pd.date_range(start, periods=minutes, freq="1min")
    buckets = np.arange(minutes) // 15
    spot_close = 100.0 + 0.04 * np.minimum(buckets, 200)
    perpetual_close = spot_close + 0.005 * np.maximum(buckets - 200, 0)
    spot_high = spot_close + 0.01
    perpetual_high = perpetual_close + 0.01
    spot_close[buckets == 224] = 112.0
    spot_high[buckets == 224] = 112.01
    perpetual_high[buckets == 220] = 110.0
    perpetual_close[buckets == 236] = 111.0
    perpetual_high[buckets == 236] = 111.01
    spot = _frame(index, spot_close, spot_high)
    perpetual = _frame(index, perpetual_close, perpetual_high)
    perpetual["funding_rate"] = 0.0
    return (
        perpetual,
        spot,
        start + pd.Timedelta(minutes=224 * 15 + 14),
        start + pd.Timedelta(minutes=228 * 15 + 14),
        start + pd.Timedelta(minutes=236 * 15 + 14),
    )


def _frame(
    index: pd.DatetimeIndex,
    close: np.ndarray,
    high: np.ndarray,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close - 0.005,
            "high": high,
            "low": close - 0.01,
            "close": close,
            "volume": 10.0,
            "gap_before_bars": 0,
        },
        index=index,
    )
