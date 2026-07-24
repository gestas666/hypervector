"""Order-book entry gate — book decides whether we trade, not only fill price.

Used on paper/shadow **enters**. Closes are never book-gated (risk-off).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hypervector.paper.book import BookSnapshot, DEFAULT_MAX_BOOK_AGE_MS


# Defaults tuned for liquid BTC perps; override via session/CLI.
DEFAULT_MAX_SPREAD_BPS = 5.0  # 5 bps = 0.05%
DEFAULT_MIN_TOUCH_SIZE = 0.01  # min size on relevant touch
DEFAULT_MIN_IMBALANCE = 0.0  # 0 = off; e.g. 0.05 requires mild pressure


@dataclass(frozen=True)
class BookGateResult:
    allow: bool
    reason: str | None
    metrics: dict[str, Any]


def book_metrics(snap: BookSnapshot) -> dict[str, Any]:
    bid = snap.best_bid()
    ask = snap.best_ask()
    bid_sz = float(snap.bids[0].size) if snap.bids else 0.0
    ask_sz = float(snap.asks[0].size) if snap.asks else 0.0
    mid = None
    spread = None
    spread_bps = None
    imbalance = None
    if bid is not None and ask is not None and ask > 0 and bid > 0:
        mid = 0.5 * (bid + ask)
        spread = ask - bid
        if mid > 0:
            spread_bps = 10_000.0 * spread / mid
        tot = bid_sz + ask_sz
        imbalance = (bid_sz - ask_sz) / tot if tot > 0 else 0.0
    return {
        "best_bid": bid,
        "best_ask": ask,
        "bid_sz": bid_sz,
        "ask_sz": ask_sz,
        "mid": mid,
        "spread": spread,
        "spread_bps": spread_bps,
        "imbalance": imbalance,  # + = bid-heavy (long-friendly)
        "n_bids": len(snap.bids),
        "n_asks": len(snap.asks),
        "source": snap.source,
    }


def evaluate_book_entry(
    snap: BookSnapshot | None,
    *,
    side: str,
    now_ms: float,
    max_age_ms: float = DEFAULT_MAX_BOOK_AGE_MS,
    max_spread_bps: float = DEFAULT_MAX_SPREAD_BPS,
    min_touch_size: float = DEFAULT_MIN_TOUCH_SIZE,
    min_imbalance: float = DEFAULT_MIN_IMBALANCE,
    require_fresh: bool = True,
) -> BookGateResult:
    """Return whether a new entry is allowed given the book.

    ``side``: ``buy`` (long enter) or ``sell`` (short enter).
    """
    side_n = str(side).lower().strip()
    if side_n not in ("buy", "sell"):
        return BookGateResult(False, f"invalid_side:{side}", {})

    if snap is None or snap.is_empty():
        if require_fresh:
            return BookGateResult(False, "book_missing", {})
        return BookGateResult(True, None, {"book": "absent_allowed"})

    age = snap.age_ms(float(now_ms))
    m = book_metrics(snap)
    m["age_ms"] = age

    if require_fresh and age > float(max_age_ms):
        return BookGateResult(False, f"book_stale:{age:.0f}ms", m)

    bid, ask = m["best_bid"], m["best_ask"]
    if bid is None or ask is None or ask <= bid:
        return BookGateResult(False, "book_crossed_or_empty", m)

    sbps = m["spread_bps"]
    if sbps is not None and sbps > float(max_spread_bps):
        return BookGateResult(False, f"spread_too_wide:{sbps:.2f}bps", m)

    # Touch liquidity on the side we hit (buy lifts ask, sell hits bid)
    touch = float(m["ask_sz"] if side_n == "buy" else m["bid_sz"])
    if touch < float(min_touch_size):
        return BookGateResult(False, f"touch_too_thin:{touch}", m)

    imb = m["imbalance"]
    if imb is not None and float(min_imbalance) > 0:
        # Long wants bid pressure (imb > +min); short wants ask pressure (imb < -min)
        if side_n == "buy" and imb < float(min_imbalance):
            return BookGateResult(False, f"imbalance_against_long:{imb:.3f}", m)
        if side_n == "sell" and imb > -float(min_imbalance):
            return BookGateResult(False, f"imbalance_against_short:{imb:.3f}", m)

    return BookGateResult(True, None, m)
