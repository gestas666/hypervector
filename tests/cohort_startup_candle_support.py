"""Offline exact-value inputs for startup candle archival tests."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

OBSERVED = datetime(2026, 8, 1, 12, tzinfo=UTC)
OBSERVED_MS = int(OBSERVED.timestamp() * 1000)


def candle_frame(rows: int = 5001) -> pd.DataFrame:
    """Include full history, a current unfinished minute and auxiliary fields."""
    values = np.arange(rows, dtype=np.float64)
    close = np.nextafter(144.0 + np.sin(values / 200.0), np.inf)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(end=OBSERVED, periods=rows, freq="min"),
            "open": close - 0.01,
            "high": close + 0.2 + values / 10000.0,
            "low": close - 0.2,
            "close": close,
            "volume": np.arange(rows, dtype=np.int64),
            "source": "hl",
            "synthetic": False,
        }
    )
