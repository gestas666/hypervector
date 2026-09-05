"""Bounded completed-candle request reuse for report-only polling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

_MINUTE_MILLISECONDS = 60_000


class CandleSnapshotFetcher(Protocol):
    """Callable contract for one bounded public candle snapshot."""

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame: ...


@dataclass(frozen=True)
class _CacheEntry:
    minute: int
    frame: pd.DataFrame


class CompletedCandleSnapshotCache:
    """Reuse a verified 1-minute snapshot within one completed-minute boundary."""

    def __init__(
        self,
        fetch: CandleSnapshotFetcher,
        *,
        uncached_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._fetch = fetch
        if any(not symbol.strip() for symbol in uncached_symbols):
            raise ValueError("uncached candle symbols must be nonempty text")
        self._uncached_symbols = uncached_symbols
        self._entries: dict[tuple[str, str], _CacheEntry] = {}

    def __call__(
        self,
        symbol: str,
        timeframe: str,
        lookback_days: float,
        *,
        end_ms: int | None = None,
    ) -> pd.DataFrame:
        """Fetch once per minute and retry responses missing the completed bar."""
        if symbol in self._uncached_symbols or timeframe != "1m" or end_ms is None:
            return self._fetch(symbol, timeframe, lookback_days, end_ms=end_ms)
        minute = _minute_bucket(end_ms)
        key = (symbol, timeframe)
        entry = self._entries.get(key)
        if entry is not None and entry.minute == minute:
            return entry.frame.copy(deep=True)
        frame = self._fetch(symbol, timeframe, lookback_days, end_ms=end_ms)
        if _contains_latest_completed_bar(frame, minute):
            self._entries[key] = _CacheEntry(minute, frame.copy(deep=True))
        return frame


def _minute_bucket(end_ms: int) -> int:
    if isinstance(end_ms, bool) or not isinstance(end_ms, int) or end_ms < 0:
        raise ValueError("candle snapshot end_ms must be a nonnegative integer")
    return end_ms // _MINUTE_MILLISECONDS


def _contains_latest_completed_bar(frame: pd.DataFrame, minute: int) -> bool:
    if frame.empty or "timestamp" not in frame.columns:
        return False
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    required_ms = (minute - 1) * _MINUTE_MILLISECONDS
    required = pd.to_datetime(required_ms, unit="ms", utc=True)
    return bool(timestamps.eq(required).any())
