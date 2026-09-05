"""Tests for deterministic BTC option-flow market-source merging."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_option_flow_source_merge import (
    merge_option_flow_candles,
    merge_option_flow_funding,
)


def test_exact_overlap_is_deduplicated_into_requested_half_open_window() -> None:
    """Primary and horizon bundles may overlap only with identical observations."""
    primary = _candles("2025-01-01T00:00:00Z", 3)
    horizon = _candles("2025-01-01T02:00:00Z", 3)

    merged = merge_option_flow_candles(
        (primary, horizon),
        start=pd.Timestamp("2025-01-01T00:00:00Z"),
        end=pd.Timestamp("2025-01-01T05:00:00Z"),
    )

    assert len(merged) == 5
    assert merged["timestamp"].is_unique


def test_conflicting_candle_or_funding_overlap_fails_closed() -> None:
    """No bundle precedence may hide a source conflict."""
    primary = _candles("2025-01-01T00:00:00Z", 3)
    horizon = _candles("2025-01-01T02:00:00Z", 2)
    horizon.loc[0, "close"] = 101.0
    with pytest.raises(ValueError, match="conflicting duplicate candles"):
        merge_option_flow_candles(
            (primary, horizon),
            start=pd.Timestamp("2025-01-01T00:00:00Z"),
            end=pd.Timestamp("2025-01-01T04:00:00Z"),
        )
    first = _funding("2025-01-01T00:00:00Z", (0.1, 0.2))
    second = _funding("2025-01-01T01:00:00Z", (0.3, 0.4))
    with pytest.raises(ValueError, match="conflicting duplicate funding"):
        merge_option_flow_funding(
            (first, second),
            start=pd.Timestamp("2025-01-01T00:00:00Z"),
            end=pd.Timestamp("2025-01-01T03:00:00Z"),
        )


def test_exact_funding_overlap_produces_complete_ordered_series() -> None:
    """Equal overlap must retain one exact event per hour."""
    first = _funding("2025-01-01T00:00:00Z", (0.1, 0.2))
    second = _funding("2025-01-01T01:00:00Z", (0.2, 0.3))

    merged = merge_option_flow_funding(
        (first, second),
        start=pd.Timestamp("2025-01-01T00:00:00Z"),
        end=pd.Timestamp("2025-01-01T03:00:00Z"),
    )

    assert merged.tolist() == [0.1, 0.2, 0.3]
    assert merged.index.equals(
        pd.date_range("2025-01-01T00:00:00Z", periods=3, freq="1h")
    )


def _candles(start: str, periods: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=periods, freq="1h"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
        }
    )


def _funding(start: str, values: tuple[float, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=len(values), freq="1h"),
            "funding_rate": values,
        }
    )
