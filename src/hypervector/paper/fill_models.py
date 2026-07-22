"""FillModel protocol, bar_close / top_bps / l2_walk models, book-aware selection.

Task 4: L2WalkFillModel (VWAP level walk) is preferred when book is fresh
and preferred_fill_model is l2_walk_v1. Missing/stale book → bar_close fallback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1 = "bar_close_slippage_v1"
FILL_MODEL_TOP_BPS_V1 = "top_bps_v1"
FILL_MODEL_L2_WALK_V1 = "l2_walk_v1"
DEFAULT_MAX_BOOK_AGE_MS = 3000


@dataclass(frozen=True)
class FillResult:
    fill_px: float
    fill_qty: float
    fill_model_id: str
    levels_used: int
    shortfall_qty: float
    bbo_bid: float | None
    bbo_ask: float | None
    book_age_ms: float | None
    fill_fallback_reason: str | None
    requested_qty: float


class FillModel(Protocol):
    fill_model_id: str

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult: ...


class BarCloseSlippageFillModel:
    """Mark ± slippage_bps; no book dependency."""

    fill_model_id = FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        slip = float(slippage_bps) / 10_000.0
        side_n = side.lower().strip()
        if side_n == "buy":
            px = float(mark_px) * (1.0 + slip)
        else:
            px = float(mark_px) * (1.0 - slip)
        q = float(qty)
        return FillResult(
            fill_px=px,
            fill_qty=q,
            fill_model_id=self.fill_model_id,
            levels_used=0,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason=None,
            requested_qty=q,
        )


class TopBpsFillModel:
    """Fill at best bid/ask ± slippage_bps; uses top of book only (levels_used=1).

    buy  = best_ask * (1 + slip)
    sell = best_bid * (1 - slip)
    Raises ValueError if book is None/empty or the required BBO side is missing.
    """

    fill_model_id = FILL_MODEL_TOP_BPS_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        if book is None or getattr(book, "is_empty", lambda: True)():
            raise ValueError("TopBpsFillModel requires a non-empty book")

        bid = book.best_bid()
        ask = book.best_ask()
        side_n = side.lower().strip()
        slip = float(slippage_bps) / 10_000.0

        if side_n == "buy":
            if ask is None:
                raise ValueError("TopBpsFillModel buy requires best_ask")
            px = float(ask) * (1.0 + slip)
        else:
            if bid is None:
                raise ValueError("TopBpsFillModel sell requires best_bid")
            px = float(bid) * (1.0 - slip)

        q = float(qty)
        book_age: float | None = None
        # Caller may have already checked freshness; still record age if ts present.
        try:
            now = time.time() * 1000.0
            book_age = float(book.age_ms(now))
        except Exception:  # noqa: BLE001 — optional diagnostic field
            book_age = None

        return FillResult(
            fill_px=px,
            fill_qty=q,
            fill_model_id=self.fill_model_id,
            levels_used=1,
            shortfall_qty=0.0,
            bbo_bid=float(bid) if bid is not None else None,
            bbo_ask=float(ask) if ask is not None else None,
            book_age_ms=book_age,
            fill_fallback_reason=None,
            requested_qty=q,
        )


class L2WalkFillModel:
    """Walk L2 levels for size-weighted average price; never invent depth.

    buy  walks asks ascending; sell walks bids descending.
    fill_qty = min(requested, available); shortfall_qty = remainder.
    Optional slippage_bps is applied on the VWAP (buy up / sell down).
    If the walked side has no size, fill_qty=0 (caller skips / falls back).
    """

    fill_model_id = FILL_MODEL_L2_WALK_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        requested = float(qty)
        if book is None or getattr(book, "is_empty", lambda: True)():
            return FillResult(
                fill_px=float(mark_px),
                fill_qty=0.0,
                fill_model_id=self.fill_model_id,
                levels_used=0,
                shortfall_qty=requested,
                bbo_bid=None,
                bbo_ask=None,
                book_age_ms=None,
                fill_fallback_reason=None,
                requested_qty=requested,
            )

        bid = book.best_bid()
        ask = book.best_ask()
        side_n = side.lower().strip()
        slip = float(slippage_bps) / 10_000.0

        if side_n == "buy":
            levels = list(getattr(book, "asks", ()) or ())
        else:
            levels = list(getattr(book, "bids", ()) or ())

        remaining = requested
        total_notional = 0.0
        filled = 0.0
        levels_used = 0

        for lvl in levels:
            if remaining <= 0:
                break
            try:
                px = float(lvl.price)
                sz = float(lvl.size)
            except (TypeError, ValueError, AttributeError):
                continue
            if sz <= 0:
                continue
            take = min(remaining, sz)
            total_notional += take * px
            filled += take
            remaining -= take
            levels_used += 1

        shortfall = requested - filled
        if filled > 0:
            vwap = total_notional / filled
            if side_n == "buy":
                fill_px = vwap * (1.0 + slip)
            else:
                fill_px = vwap * (1.0 - slip)
        else:
            # No depth on walked side — do not invent; engine should skip.
            fill_px = float(mark_px)

        book_age: float | None = None
        try:
            now = time.time() * 1000.0
            book_age = float(book.age_ms(now))
        except Exception:  # noqa: BLE001 — optional diagnostic field
            book_age = None

        return FillResult(
            fill_px=fill_px,
            fill_qty=filled,
            fill_model_id=self.fill_model_id,
            levels_used=levels_used,
            shortfall_qty=shortfall,
            bbo_bid=float(bid) if bid is not None else None,
            bbo_ask=float(ask) if ask is not None else None,
            book_age_ms=book_age,
            fill_fallback_reason=None,
            requested_qty=requested,
        )


def select_fill_model(
    *,
    preferred: str,
    book: Any | None,
    max_book_age_ms: float,
    now_ms: float | None = None,
) -> tuple[FillModel, str | None]:
    """Pick a fill model based on preferred id and book freshness.

    Returns ``(model, fill_fallback_reason)``. Reason is set when falling back
    to bar_close because the book is missing/empty or stale.

    Selection rules:
    - preferred bar_close → BarClose, reason None
    - book None or empty → BarClose, ``book_missing``
    - book.age_ms(now) > max → BarClose, ``book_stale``
    - preferred top_bps with fresh book → TopBps, None
    - preferred l2_walk with fresh book → L2Walk, None

    Unknown preferred values with a fresh book fall back to bar_close with no
    reason (same as Task 1 scaffold for unwired models).
    """
    preferred_n = str(preferred).strip()
    if preferred_n == FILL_MODEL_BAR_CLOSE_SLIPPAGE_V1:
        return BarCloseSlippageFillModel(), None

    if book is None or getattr(book, "is_empty", lambda: True)():
        return BarCloseSlippageFillModel(), "book_missing"

    now = float(now_ms) if now_ms is not None else time.time() * 1000.0
    age = float(book.age_ms(now))
    if age > float(max_book_age_ms):
        return BarCloseSlippageFillModel(), "book_stale"

    if preferred_n == FILL_MODEL_TOP_BPS_V1:
        return TopBpsFillModel(), None
    if preferred_n == FILL_MODEL_L2_WALK_V1:
        return L2WalkFillModel(), None

    # Unknown preferred with usable book → keep bar_close (no silent switch).
    return BarCloseSlippageFillModel(), None
