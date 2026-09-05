"""Completed-candle transport cache tests for report-only observers."""

from __future__ import annotations

import pandas as pd

from hypervector.live.completed_candle_snapshot_cache import (
    CompletedCandleSnapshotCache,
)

_MINUTE_MS = 60_000


def test_reuses_one_snapshot_inside_the_same_completed_minute() -> None:
    """Repeated polls must not refetch an unchanged completed-minute boundary."""
    calls: list[int | None] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del symbol, timeframe, lookback_days
        calls.append(end_ms)
        return _bars(100 * _MINUTE_MS)

    cached = CompletedCandleSnapshotCache(fetch)
    first = cached("BTC", "1m", 1.0, end_ms=101 * _MINUTE_MS + 1_000)
    first.loc[0, "close"] = 999.0
    second = cached("BTC", "1m", 1.0, end_ms=101 * _MINUTE_MS + 45_000)

    assert calls == [101 * _MINUTE_MS + 1_000]
    assert second.loc[0, "close"] == 100.0


def test_refreshes_at_the_next_completed_minute_boundary() -> None:
    """A new minute must fetch the candle that has just become complete."""
    calls: list[int | None] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del symbol, timeframe, lookback_days
        calls.append(end_ms)
        assert end_ms is not None
        return _bars((end_ms // _MINUTE_MS - 1) * _MINUTE_MS)

    cached = CompletedCandleSnapshotCache(fetch)
    cached("ETH", "1m", 1.0, end_ms=101 * _MINUTE_MS + 15_000)
    cached("ETH", "1m", 1.0, end_ms=102 * _MINUTE_MS + 15_000)

    assert len(calls) == 2


def test_missing_completed_bar_is_not_cached() -> None:
    """An early or incomplete response must be retried rather than frozen."""
    calls = 0

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        nonlocal calls
        del symbol, timeframe, lookback_days, end_ms
        calls += 1
        return _bars(99 * _MINUTE_MS if calls == 1 else 100 * _MINUTE_MS)

    cached = CompletedCandleSnapshotCache(fetch)
    cached("SOL", "1m", 1.0, end_ms=101 * _MINUTE_MS + 1_000)
    cached("SOL", "1m", 1.0, end_ms=101 * _MINUTE_MS + 15_000)

    assert calls == 2


def test_current_in_progress_bar_cannot_mask_missing_completed_bar() -> None:
    """The exact required close must exist before a response is reusable."""
    calls = 0

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        nonlocal calls
        del symbol, timeframe, lookback_days, end_ms
        calls += 1
        return _bars((101 if calls == 1 else 100) * _MINUTE_MS)

    cached = CompletedCandleSnapshotCache(fetch)
    cached("HYPE", "1m", 1.0, end_ms=101 * _MINUTE_MS + 1_000)
    cached("HYPE", "1m", 1.0, end_ms=101 * _MINUTE_MS + 15_000)

    assert calls == 2


def test_explicit_symbol_bypass_preserves_every_transport_observation() -> None:
    """Lock-sensitive symbols must refetch even inside one minute boundary."""
    calls: list[str] = []

    def fetch(
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        del timeframe, lookback_days, end_ms
        calls.append(symbol)
        return _bars(100 * _MINUTE_MS)

    cached = CompletedCandleSnapshotCache(
        fetch,
        uncached_symbols=frozenset({"xyz:SP500"}),
    )
    for symbol in ("BTC", "xyz:SP500"):
        cached(symbol, "1m", 1.0, end_ms=101 * _MINUTE_MS + 1_000)
        cached(symbol, "1m", 1.0, end_ms=101 * _MINUTE_MS + 15_000)

    assert calls == ["BTC", "xyz:SP500", "xyz:SP500"]


def _bars(timestamp_ms: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [pd.to_datetime(timestamp_ms, unit="ms", utc=True)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
            "volume": [10.0],
        }
    )
