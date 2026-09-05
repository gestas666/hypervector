"""Deterministic fixtures for IBIT creation-persistence research tests."""

from __future__ import annotations

import pandas as pd


def ibit_creation_history() -> pd.DataFrame:
    """Return one second-positive creation onset available August 3 at noon."""
    return pd.DataFrame(
        {
            "as_of_date": pd.to_datetime(["2026-07-31", "2026-08-01", "2026-08-02"]),
            "nav_per_share": [30.0, 30.0, 30.0],
            "shares_outstanding": [100, 110, 120],
        }
    )


def ibit_market(hours: int = 110) -> pd.DataFrame:
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
