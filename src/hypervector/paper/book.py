"""Order book snapshot + BookFeed for Phase 4a paper fills.

HL L2 REST is the v1 transport; fill models (top_bps / l2_walk) consume
BookSnapshot in later tasks. Staleness helpers live here (SRS_HV4A_STALE).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_BOOK_AGE_MS = 3000.0


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class BookSnapshot:
    symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    ts_recv_ms: float
    ts_exchange_ms: float | None
    source: str

    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    def is_empty(self) -> bool:
        return not self.bids and not self.asks

    def age_ms(self, now_ms: float) -> float:
        """Age relative to exchange ts when set, else receive ts."""
        base = self.ts_exchange_ms if self.ts_exchange_ms is not None else self.ts_recv_ms
        return float(now_ms) - float(base)


@dataclass(frozen=True)
class BookMicrostructure:
    """Measured top-of-book and depth metrics for display telemetry."""

    mid_price: float
    spread_bps: float
    bid_depth: float
    ask_depth: float
    bid_depth_ratio: float
    order_pressure_index: float


def summarize_book(
    snapshot: BookSnapshot,
    *,
    depth_levels: int = 5,
) -> BookMicrostructure:
    """Calculate microstructure metrics from observed L2 levels."""
    if depth_levels <= 0:
        raise ValueError("depth_levels must be positive")
    if not snapshot.bids or not snapshot.asks:
        raise ValueError("book telemetry requires non-empty bid and ask sides")
    best_bid = snapshot.bids[0].price
    best_ask = snapshot.asks[0].price
    mid_price = (best_bid + best_ask) / 2.0
    if mid_price <= 0.0 or best_ask < best_bid:
        raise ValueError("book telemetry requires a positive, non-crossed market")
    bid_depth = sum(level.size for level in snapshot.bids[:depth_levels])
    ask_depth = sum(level.size for level in snapshot.asks[:depth_levels])
    total_depth = bid_depth + ask_depth
    if bid_depth < 0.0 or ask_depth <= 0.0 or total_depth <= 0.0:
        raise ValueError("book telemetry requires positive observed depth")
    return BookMicrostructure(
        mid_price=mid_price,
        spread_bps=(best_ask - best_bid) / mid_price * 10_000.0,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        bid_depth_ratio=bid_depth / ask_depth,
        order_pressure_index=(bid_depth - ask_depth) / total_depth,
    )


def _parse_level(item: Any) -> BookLevel | None:
    try:
        if isinstance(item, dict):
            return BookLevel(price=float(item["px"]), size=float(item["sz"]))
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            return BookLevel(price=float(item[0]), size=float(item[1]))
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return None


def _parse_side(raw_levels: Any) -> list[BookLevel]:
    if not isinstance(raw_levels, list):
        return []
    out: list[BookLevel] = []
    for item in raw_levels:
        lvl = _parse_level(item)
        if lvl is not None:
            out.append(lvl)
    return out


def parse_hl_l2_payload(
    raw: Any,
    *,
    symbol: str,
    ts_recv_ms: float,
    source: str = "hl_rest_l2",
) -> BookSnapshot:
    """Parse HL info ``l2Book`` payload into a BookSnapshot.

    Expected shape: ``{"levels": [bids, asks], "time": <ms optional>}``.
    Each level is ``{"px", "sz"}`` or a length-2 sequence ``[px, sz]``.
    Bids are sorted price descending; asks ascending.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"HL l2Book payload must be a dict, got {type(raw).__name__}")

    levels = raw.get("levels")
    if not isinstance(levels, (list, tuple)) or len(levels) < 2:
        raise ValueError("HL l2Book payload missing levels[bids, asks]")

    bids = _parse_side(levels[0])
    asks = _parse_side(levels[1])
    bids.sort(key=lambda x: x.price, reverse=True)
    asks.sort(key=lambda x: x.price)

    ts_exchange_ms: float | None = None
    if "time" in raw and raw["time"] is not None:
        try:
            ts_exchange_ms = float(raw["time"])
        except (TypeError, ValueError):
            ts_exchange_ms = None

    return BookSnapshot(
        symbol=symbol,
        bids=tuple(bids),
        asks=tuple(asks),
        ts_recv_ms=float(ts_recv_ms),
        ts_exchange_ms=ts_exchange_ms,
        source=source,
    )


class BookFeed:
    """Latest-book holder with freshness tracking (max_age_ms default 3000)."""

    def __init__(self, symbol: str, *, max_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS) -> None:
        self.symbol = symbol
        self.max_age_ms = float(max_age_ms)
        self._latest: BookSnapshot | None = None

    def update(self, snap: BookSnapshot) -> None:
        self._latest = snap

    def latest(self) -> BookSnapshot | None:
        return self._latest

    def is_fresh(self, *, now_ms: float | None = None) -> bool:
        snap = self._latest
        if snap is None or snap.is_empty():
            return False
        now = float(now_ms) if now_ms is not None else time.time() * 1000.0
        return snap.age_ms(now) <= self.max_age_ms

    def poll(self, *, session: Any | None = None) -> BookSnapshot | None:
        """Fetch L2 via HL REST, update cache. Returns None on failure."""
        try:
            # Module-level name so tests can patch hypervector.paper.book.fetch_hl_l2_book
            snap = fetch_hl_l2_book(self.symbol, session=session)
        except Exception as exc:  # noqa: BLE001 — poll must never raise
            logger.warning("BookFeed.poll failed for %s: %s", self.symbol, exc)
            return None
        self.update(snap)
        return snap


def fetch_hl_l2_book(symbol: str, *, session: Any | None = None) -> BookSnapshot:
    """Delegate to ``data.hl.fetch_hl_l2_book`` (patchable for tests)."""
    from hypervector.data.hl import fetch_hl_l2_book as _fetch

    return _fetch(symbol, session=session)
