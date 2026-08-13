"""Stateful, timestamp-deduplicated market observations for Apex MM."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Literal

from hypervector.live.hyperliquid_protocol import SolBookSnapshot

_CASCADE_TRIGGER_BPS = 20.0
_VOLATILITY_RETURN_WINDOW = 20


@dataclass(frozen=True)
class ApexMMMarketObservation:
    """Derived cascade and recent midpoint-volatility state."""

    cascade_side: Literal["none", "down", "up"]
    volatility_bps: float


class ApexMMMarketTracker:
    """Consume each exchange-timestamped book at most once."""

    def __init__(self) -> None:
        self._previous_mid: float | None = None
        self._previous_book_ts_ms: int | None = None
        self._cascade_side: Literal["none", "down", "up"] = "none"
        self._mid_returns: deque[float] = deque(maxlen=_VOLATILITY_RETURN_WINDOW)

    def observe(self, book: SolBookSnapshot) -> ApexMMMarketObservation:
        """Update derived state only for a new exchange book timestamp."""
        if book.exchange_timestamp_ms != self._previous_book_ts_ms:
            self._cascade_side = self._cascade(book.mid_price)
            if self._previous_mid is not None:
                self._mid_returns.append(math.log(book.mid_price / self._previous_mid))
            self._previous_mid = book.mid_price
            self._previous_book_ts_ms = book.exchange_timestamp_ms
        return ApexMMMarketObservation(self._cascade_side, self._volatility_bps())

    def _cascade(self, midpoint: float) -> Literal["none", "down", "up"]:
        if self._previous_mid is None:
            return "none"
        move_bps = (midpoint / self._previous_mid - 1.0) * 10_000.0
        if move_bps <= -_CASCADE_TRIGGER_BPS:
            return "down"
        if move_bps >= _CASCADE_TRIGGER_BPS:
            return "up"
        return "none"

    def _volatility_bps(self) -> float:
        if len(self._mid_returns) < 2:
            return 0.0
        mean = sum(self._mid_returns) / len(self._mid_returns)
        variance = sum((value - mean) ** 2 for value in self._mid_returns) / len(
            self._mid_returns
        )
        return math.sqrt(variance) * 10_000.0
