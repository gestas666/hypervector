"""Tests for causal five-to-fifteen-minute Cipher bar aggregation."""

from __future__ import annotations

from datetime import UTC

import pandas as pd

from hypervector.research.cipher_suite_timeframes import (
    align_cipher_bundle_timeframes,
    resample_cipher_bars,
)


def _bars() -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=9, freq="5min", tz=UTC)
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "open": [100.0 + index for index in range(9)],
            "high": [101.0 + index for index in range(9)],
            "low": [99.0 + index for index in range(9)],
            "close": [100.5 + index for index in range(9)],
            "volume": [1.0] * 9,
        }
    )


def test_fifteen_minute_bars_use_only_three_complete_closed_bars() -> None:
    """15m OHLCV must aggregate three observed 5m bars without future leakage."""
    output = resample_cipher_bars(_bars(), bar_minutes=15)

    assert len(output) == 3
    assert output.loc[0, "open"] == 100.0
    assert output.loc[0, "high"] == 103.0
    assert output.loc[0, "low"] == 99.0
    assert output.loc[0, "close"] == 102.5
    assert output.loc[0, "volume"] == 3.0


def test_incomplete_fifteen_minute_bucket_is_dropped() -> None:
    """A missing constituent bar must not fabricate a 15m candle."""
    bars = _bars().drop(index=4).reset_index(drop=True)

    output = resample_cipher_bars(bars, bar_minutes=15)

    assert output["bar_open_at"].tolist() == [
        pd.Timestamp("2026-01-01T00:00:00Z"),
        pd.Timestamp("2026-01-01T00:30:00Z"),
    ]


def test_thirty_minute_bars_require_six_complete_constituents() -> None:
    """Recovered Hulk research must not fabricate incomplete 30m bars."""
    complete = (
        pd.concat(
            [
                _bars(),
                _bars().assign(
                    bar_open_at=lambda frame: frame["bar_open_at"]
                    + pd.Timedelta(minutes=45)
                ),
            ]
        )
        .sort_values("bar_open_at")
        .reset_index(drop=True)
    )

    output = resample_cipher_bars(complete, bar_minutes=30)

    assert len(output) == 3
    assert output.loc[0, "open"] == 100.0
    assert output.loc[0, "close"] == 105.5
    assert output.loc[0, "volume"] == 6.0


def test_bundle_alignment_uses_only_closed_fresh_fifteen_minute_trend() -> None:
    """A 15m context may reach 5m triggers only after that 15m bar closes."""
    execution_index = pd.date_range("2026-01-01T00:00:00Z", periods=8, freq="5min")
    execution = pd.DataFrame(
        {
            "cipher_a_trend": [0] * 8,
            "cipher_b_trigger": [0, 0, 0, 1, 0, -1, 1, 0],
            "cipher_b_cross_trigger": [0, 1, 0, 1, 0, -1, 1, 0],
            "cipher_b_money_flow": [1] * 8,
            "cipher_dbsi": [1] * 8,
        },
        index=execution_index,
    )
    trend_index = pd.DatetimeIndex(["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"])
    trend = pd.DataFrame(
        {
            "cipher_a_trend": [1, -1],
            "cipher_b_trigger": [0, 0],
            "cipher_b_cross_trigger": [0, 0],
            "cipher_b_money_flow": [0, 0],
            "cipher_dbsi": [0, 0],
        },
        index=trend_index,
    )

    aligned = align_cipher_bundle_timeframes(execution, trend, trend_minutes=15)

    assert aligned["cipher_a_trend"].tolist() == [0, 0, 0, 1, 1, 1, 0, 0]
    assert aligned["cipher_b_trigger"].equals(execution["cipher_b_trigger"])
