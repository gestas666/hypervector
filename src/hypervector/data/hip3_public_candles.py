"""Unsigned bounded Hyperliquid candle source for HIP-3 research commands."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from hypervector.data.hl import fetch_hl_ohlcv_snapshot

_DAY_MS = 86_400_000
_INTERVALS = {1: "1m", 5: "5m", 15: "15m"}


class Hip3CandleSourceProtocol(Protocol):
    """Return bounded completed public candles without signing authority."""

    def completed_candles(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        observed_at_ms: int,
        timeframe_minutes: int = 15,
    ) -> pd.DataFrame:
        """Return venue candles overlapping one explicit comparison scope."""


class Hip3PublicCandleSource:
    """Fetch unsigned Hyperliquid candleSnapshot evidence."""

    def completed_candles(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        observed_at_ms: int,
        timeframe_minutes: int = 15,
    ) -> pd.DataFrame:
        """Fetch a bounded public candle snapshot at the explicit cadence."""
        del end_ms
        try:
            interval = _INTERVALS[timeframe_minutes]
        except (KeyError, TypeError) as exc:
            raise ValueError("HIP-3 candle timeframe is unsupported") from exc
        lookback_days = max((observed_at_ms - start_ms) / _DAY_MS + 0.25, 0.5)
        return fetch_hl_ohlcv_snapshot(
            symbol,
            interval,
            lookback_days,
            end_ms=observed_at_ms,
        )
