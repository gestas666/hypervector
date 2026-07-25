"""Causal post-only mechanics for the Hypervelocity paper backend."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import floor, log10
from typing import Any, Literal

import pandas as pd

from hypervector.paper.fill_models import FillResult

Direction = Literal["long", "short"]

FILL_MODEL_POST_ONLY_LIMIT_THROUGH_V1 = "post_only_limit_through_v1"
DEFAULT_ENTRY_TTL_SECONDS = 300.0


def hyperliquid_price_tick(price: float, *, size_decimals: int) -> float:
    """Return the valid perp price step under Hyperliquid's precision rules."""
    value = float(price)
    if value <= 0.0:
        raise ValueError("price must be positive")
    if not 0 <= int(size_decimals) <= 6:
        raise ValueError("size_decimals must be between 0 and 6")
    significant_exponent = floor(log10(value)) - 4
    decimal_cap_exponent = -(6 - int(size_decimals))
    tick_exponent = min(0, max(significant_exponent, decimal_cap_exponent))
    return float(10.0**tick_exponent)


def round_price_to_tick(
    price: float,
    *,
    tick_size: float,
    upward: bool,
) -> float:
    """Round a price outward to an exact venue tick."""
    tick = Decimal(str(tick_size))
    if tick <= 0:
        raise ValueError("tick_size must be positive")
    rounding = ROUND_CEILING if upward else ROUND_FLOOR
    units = (Decimal(str(price)) / tick).to_integral_value(rounding=rounding)
    return float(units * tick)


def quantize_size_down(qty: float, *, size_decimals: int) -> float:
    """Round position size down to the venue's allowed size precision."""
    if not 0 <= int(size_decimals) <= 18:
        raise ValueError("size_decimals must be between 0 and 18")
    quantum = Decimal(1).scaleb(-int(size_decimals))
    value = Decimal(str(qty)).quantize(quantum, rounding=ROUND_FLOOR)
    return float(value)


@dataclass(frozen=True)
class PendingMakerEntry:
    """One unfilled post-only entry retained across completed bars."""

    direction: Direction
    qty: float
    limit_price: float
    submitted_at: pd.Timestamp
    conviction: float | None = None
    conviction_source: str | None = None
    metalabel_p: float | None = None
    metalabel_bundle_id: str | None = None

    @property
    def side(self) -> Literal["buy", "sell"]:
        """Return the venue side for this entry."""
        return "buy" if self.direction == "long" else "sell"

    @property
    def action(self) -> Literal["enter_long", "enter_short"]:
        """Return the backend fill action for this entry."""
        return "enter_long" if self.direction == "long" else "enter_short"


class PostOnlyLimitFillModel:
    """Fill an already-qualified maker order at its exact resting limit."""

    fill_model_id = FILL_MODEL_POST_ONLY_LIMIT_THROUGH_V1

    def fill(
        self,
        *,
        side: str,
        qty: float,
        mark_px: float,
        book: Any | None,
        slippage_bps: float,
    ) -> FillResult:
        """Return a full exact-price fill after external through validation."""
        del side, book, slippage_bps
        quantity = float(qty)
        price = float(mark_px)
        return FillResult(
            fill_px=price,
            fill_qty=quantity,
            fill_model_id=self.fill_model_id,
            levels_used=0,
            shortfall_qty=0.0,
            bbo_bid=None,
            bbo_ask=None,
            book_age_ms=None,
            fill_fallback_reason=None,
            requested_qty=quantity,
        )


def entry_limit_price(
    direction: Direction,
    record: dict[str, Any],
    *,
    book: Any | None,
) -> float:
    """Choose same-side touch when available, otherwise completed-bar close."""
    if book is not None and not getattr(book, "is_empty", lambda: True)():
        touch = book.best_bid() if direction == "long" else book.best_ask()
        if touch is not None and float(touch) > 0.0:
            return float(touch)
    return float(record["close"])


def entry_was_filled(
    order: PendingMakerEntry,
    record: dict[str, Any],
    *,
    book: Any | None,
    tick_size: float,
) -> bool:
    """Return conservative one-tick-through evidence for an entry fill."""
    if book is not None and not getattr(book, "is_empty", lambda: True)():
        observed = book.best_ask() if order.direction == "long" else book.best_bid()
        if observed is not None:
            return _through(
                direction=order.direction,
                observed=float(observed),
                limit_price=order.limit_price,
                tick_size=tick_size,
                is_entry=True,
            )
    observed = float(record["low"] if order.direction == "long" else record["high"])
    return _through(
        direction=order.direction,
        observed=observed,
        limit_price=order.limit_price,
        tick_size=tick_size,
        is_entry=True,
    )


def target_was_filled(
    *,
    direction: Direction,
    target_price: float,
    record: dict[str, Any],
    book: Any | None,
    tick_size: float,
) -> bool:
    """Return conservative one-tick-through evidence for a maker target."""
    if book is not None and not getattr(book, "is_empty", lambda: True)():
        observed = book.best_bid() if direction == "long" else book.best_ask()
        if observed is not None:
            return _through(
                direction=direction,
                observed=float(observed),
                limit_price=target_price,
                tick_size=tick_size,
                is_entry=False,
            )
    observed = float(record["high"] if direction == "long" else record["low"])
    return _through(
        direction=direction,
        observed=observed,
        limit_price=target_price,
        tick_size=tick_size,
        is_entry=False,
    )


def _through(
    *,
    direction: Direction,
    observed: float,
    limit_price: float,
    tick_size: float,
    is_entry: bool,
) -> bool:
    threshold = float(tick_size)
    if threshold <= 0.0:
        raise ValueError("tick_size must be positive")
    lower_is_fill = (direction == "long") == is_entry
    if lower_is_fill:
        return observed <= float(limit_price) - threshold
    return observed >= float(limit_price) + threshold
