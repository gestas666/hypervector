"""Explicit window and market identity for 0xArchive traded candles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from hypervector.data.oxa_api import (
    API_ROOT,
    MarketFamily,
    validate_market_symbol,
    validate_window,
)

CandleInterval = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
_INTERVALS = frozenset(("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"))


@dataclass(frozen=True)
class OxaCandleRequest:
    """Explicit bounds and case-sensitive identity for one OHLCV request."""

    symbol: str
    start: datetime
    end: datetime
    interval: CandleInterval = "1m"
    limit: int = 10_000
    max_pages: int = 20
    timeout_seconds: float = 30.0
    market_family: MarketFamily = "core"

    def __post_init__(self) -> None:
        validate_market_symbol(self.symbol, self.market_family)
        validate_window(self.start, self.end)
        if self.interval not in _INTERVALS:
            raise ValueError("unsupported candle interval")
        if not 1 <= self.limit <= 10_000:
            raise ValueError("candle limit must be between 1 and 10000")
        if self.max_pages < 1 or self.timeout_seconds <= 0.0:
            raise ValueError("candle max_pages and timeout must be positive")

    def params(self, cursor: str | None = None) -> dict[str, int | str]:
        """Build bounded candle query parameters without credentials."""
        params: dict[str, int | str] = {
            "start": int(self.start.timestamp() * 1000),
            "end": int(self.end.timestamp() * 1000),
            "interval": self.interval,
            "limit": self.limit,
        }
        if cursor is not None:
            params["cursor"] = cursor
        return params

    def route(self, *, symbol: str | None = None) -> str:
        """Return the exact family endpoint or its provenance template."""
        prefix = "/hip3" if self.market_family == "hip3" else ""
        return f"{prefix}/candles/{self.symbol if symbol is None else symbol}"

    @property
    def source(self) -> str:
        """Return the family-qualified source identifier."""
        family = "_hip3" if self.market_family == "hip3" else ""
        return f"0xarchive_hyperliquid{family}_candles"

    @property
    def source_api(self) -> str:
        """Return the absolute family endpoint template for persisted evidence."""
        return f"{API_ROOT}{self.route(symbol='{symbol}')}"
