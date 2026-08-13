"""Bounded chart-history tests for multi-asset cohort telemetry."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.live.multi_asset_market_bars import (
    MultiAssetIntentPollerError,
    completed_market_bars,
    resample_one_minute_bars,
)


def test_completed_market_bars_retain_twelve_thirty_minute_bars_of_context() -> None:
    """The backend publishes six hours for twelve completed 30-minute bars."""
    timestamps = pd.date_range("2026-08-01T00:00:00Z", periods=400, freq="1min")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(100, 500),
            "high": range(101, 501),
            "low": range(99, 499),
            "close": range(100, 500),
            "volume": [10.0] * 400,
        }
    )

    output = completed_market_bars(
        bars,
        timestamps[-1] + pd.Timedelta(minutes=1),
        "BTC",
    )

    assert len(output) == 360
    assert output[0].timestamp_ms == int(timestamps[40].timestamp() * 1_000)


def test_completed_market_bars_support_explicit_exit_history_limit() -> None:
    """Lifecycle exits can request more history without inflating chart payloads."""
    timestamps = pd.date_range("2026-08-01T00:00:00Z", periods=500, freq="1min")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(100, 600),
            "high": range(101, 601),
            "low": range(99, 599),
            "close": range(100, 600),
            "volume": [10.0] * 500,
        }
    )

    output = completed_market_bars(
        bars,
        timestamps[-1] + pd.Timedelta(minutes=1),
        "BTC",
        limit=480,
    )

    assert len(output) == 480
    with pytest.raises(MultiAssetIntentPollerError, match="limit must be positive"):
        completed_market_bars(bars, timestamps[-1], "BTC", limit=0)


def test_resamples_only_complete_fifteen_minute_windows() -> None:
    """HIP-3 collectors receive no partial 15-minute decision candle."""
    timestamps = pd.date_range("2026-08-07T00:00:00Z", periods=29, freq="1min")
    bars = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": range(100, 129),
            "high": range(101, 130),
            "low": range(99, 128),
            "close": range(100, 129),
            "volume": [1.0] * 29,
        }
    )

    output = resample_one_minute_bars(bars, minutes=15)

    assert len(output) == 1
    assert output.iloc[0]["open"] == 100
    assert output.iloc[0]["close"] == 114
