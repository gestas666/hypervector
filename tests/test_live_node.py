"""Causal live-feed partitioning tests."""

from __future__ import annotations

import pandas as pd

from hypervector.paper.live_node import partition_live_bars


def _bars(*timestamps: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(list(timestamps), utc=True),
            "open": [100.0] * len(timestamps),
            "high": [101.0] * len(timestamps),
            "low": [99.0] * len(timestamps),
            "close": [100.0] * len(timestamps),
            "volume": [1.0] * len(timestamps),
        }
    )


def test_partition_seeds_catchup_and_withholds_incomplete_candle() -> None:
    frame = _bars(
        "2026-07-25T14:58:00Z",
        "2026-07-25T14:59:00Z",
        "2026-07-25T15:00:00Z",
    )

    catchup, live = partition_live_bars(
        frame,
        timeframe="1m",
        activated_at=pd.Timestamp("2026-07-25T15:00:30Z"),
        observed_at=pd.Timestamp("2026-07-25T15:00:45Z"),
    )

    assert catchup["timestamp"].tolist() == list(
        pd.to_datetime(["2026-07-25T14:58:00Z", "2026-07-25T14:59:00Z"], utc=True)
    )
    assert live.empty


def test_partition_releases_first_post_activation_completed_candle() -> None:
    frame = _bars("2026-07-25T15:00:00Z", "2026-07-25T15:01:00Z")

    catchup, live = partition_live_bars(
        frame,
        timeframe="1m",
        activated_at=pd.Timestamp("2026-07-25T15:00:30Z"),
        observed_at=pd.Timestamp("2026-07-25T15:01:05Z"),
    )

    assert catchup.empty
    assert live["timestamp"].tolist() == list(
        pd.to_datetime(["2026-07-25T15:00:00Z"], utc=True)
    )

