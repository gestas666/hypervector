from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import ema


def pullback_reacceleration_bars() -> tuple[pd.DataFrame, pd.Timestamp]:
    """Return deterministic minute bars with one causal long signal."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    baseline_hours = 60
    index = pd.date_range(start, periods=baseline_hours * 60 + 75, freq="1min")
    prices = 100.0 + np.floor(np.arange(len(index)) / 60.0)
    bars = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.01,
            "low": prices - 0.01,
            "close": prices,
            "volume": np.ones(len(index)),
        },
        index=index,
    )
    hourly_close = pd.Series(100.0 + np.arange(baseline_hours), dtype=float)
    pullback_line = float(ema(hourly_close, 21).iloc[-1])
    segment_prices = (
        pullback_line + 0.10,
        pullback_line + 0.20,
        pullback_line + 0.30,
        pullback_line + 0.40,
        pullback_line + 1.00,
    )
    for offset, price in enumerate(segment_prices):
        segment = bars.index[baseline_hours * 60 + offset * 15 :][:15]
        bars.loc[segment, ["open", "close"]] = price
        bars.loc[segment, "high"] = price + 0.01
        bars.loc[segment, "low"] = price - 0.01
    pullback_segment = bars.index[baseline_hours * 60 :][:15]
    bars.loc[pullback_segment[0], "low"] = pullback_line - 0.01
    expected = start + pd.Timedelta(hours=61, minutes=14)
    return bars, expected


def partitioned_market(hours: int = 216) -> pd.DataFrame:
    """Return continuous rising minute bars for three bounded partitions."""
    index = pd.date_range("2025-01-01", periods=hours * 60, freq="1min", tz="UTC")
    hourly = np.floor(np.arange(len(index)) / 60.0)
    close = 120.0 + hourly * 0.05
    bars = pd.DataFrame(
        {
            "open": close - 0.025,
            "high": close + 0.10,
            "low": close - 0.125,
            "close": close,
            "volume": np.ones(len(index)),
            "funding_rate": np.zeros(len(index)),
        },
        index=index,
    )
    return bars
