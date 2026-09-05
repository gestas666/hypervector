from __future__ import annotations

import numpy as np
import pandas as pd


def negative_funding_breakout_bars() -> tuple[
    pd.DataFrame,
    pd.Series,
    pd.Timestamp,
    pd.Timestamp,
]:
    """Return two hourly breakout onsets with only the second under negative funding."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    completed_hours = 63
    index = pd.date_range(start, periods=completed_hours * 60 + 1, freq="1min")
    hour = np.minimum(np.arange(len(index)) // 60, completed_hours - 1)
    hourly_close = np.where(hour < 40, 100.0 + hour * 0.10, 103.80)
    hourly_close[hour == 60] = 110.0
    hourly_close[hour == 61] = 109.0
    hourly_close[hour == 62] = 111.0
    bars = pd.DataFrame(
        {
            "open": hourly_close,
            "high": hourly_close + 0.01,
            "low": hourly_close - 0.01,
            "close": hourly_close,
            "volume": np.ones(len(index)),
        },
        index=index,
    )
    funding_index = pd.date_range(start, periods=64, freq="1h")
    funding = pd.Series(0.00001, index=funding_index, name="funding_rate")
    funding.loc[start + pd.Timedelta(hours=62)] = -0.00001
    positive_control_time = start + pd.Timedelta(hours=60, minutes=59)
    negative_candidate_time = start + pd.Timedelta(hours=62, minutes=59)
    return bars, funding, positive_control_time, negative_candidate_time


def partitioned_negative_funding_breakout_bars() -> tuple[pd.DataFrame, pd.Series]:
    """Return three contiguous 63-hour windows with causal funding events."""
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    hours = 189
    index = pd.date_range(start, periods=hours * 60, freq="1min")
    hour = np.arange(len(index)) // 60
    close = 100.0 + hour * 0.10
    bars = pd.DataFrame(
        {
            "open": close,
            "high": close + 0.01,
            "low": close - 0.01,
            "close": close,
            "volume": np.ones(len(index)),
            "funding_rate": np.zeros(len(index)),
        },
        index=index,
    )
    funding_index = pd.date_range(start, periods=hours, freq="1h")
    funding = pd.Series(0.00001, index=funding_index, name="funding_rate")
    for offset in (60, 123, 186):
        funding.loc[start + pd.Timedelta(hours=offset)] = -0.00001
    return bars, funding
