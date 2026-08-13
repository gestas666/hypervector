"""Validated recorded-book primitives for report-only depth replays."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    payload,
    text,
    text_list,
)
from hypervector.research.market_depth_fill import DepthLevel, walk_market_order

Record = Mapping[str, object]


def compatible_run_ids(contract: Record) -> tuple[str, ...]:
    """Return unique source-first observer epochs from a policy contract."""
    raw = contract.get("compatible_run_ids")
    run_ids = (
        tuple(text_list(raw, "compatible run ids"))
        if raw is not None
        else (text(contract.get("source_run_id"), "source run id"),)
    )
    if len(set(run_ids)) != len(run_ids) or run_ids[0] != contract.get("source_run_id"):
        raise ValueError("compatible run ids must be unique and source-first")
    return run_ids


def validated_books(
    records: Sequence[Record], *, symbol: str, run_ids: Sequence[str]
) -> tuple[Record, ...]:
    """Validate and order books across exact-contract observer restarts."""
    allowed = tuple(run_ids)
    if not allowed or len(set(allowed)) != len(allowed):
        raise ValueError("asset book run ids must be unique and non-empty")
    rows = tuple(event_rows(records, "book_observation"))
    for row in rows:
        values = payload(row)
        if row.get("run_id") not in allowed or values.get("symbol") != symbol:
            raise ValueError("asset book identity differs from policy contract")
        recv = book_time(row)
        exchange = nonnegative_int(values.get("exchange_ts_ms"), "exchange time")
        if exchange > recv:
            raise ValueError("asset book exchange time follows receive time")
        bids = _levels(values.get("bids"), "sell")
        asks = _levels(values.get("asks"), "buy")
        if bids[0].price >= asks[0].price:
            raise ValueError("asset book is crossed")
    ordered = tuple(sorted(rows, key=book_time))
    times = tuple(book_time(row) for row in ordered)
    if len(times) != len(set(times)):
        raise ValueError("asset book receive timestamps must be unique")
    return ordered


def visible_depth_fill(
    book: Record,
    *,
    position_side: str,
    notional: float,
    quantity: float | None,
) -> dict[str, object]:
    """Return one exact finite-depth entry or closing VWAP result."""
    market_side = "buy" if position_side == "long" else "sell"
    if quantity is not None:
        market_side = "sell" if position_side == "long" else "buy"
    levels = _levels(
        payload(book).get("asks" if market_side == "buy" else "bids"), market_side
    )
    requested = quantity or notional / levels[0].price
    fill = walk_market_order(levels, side=market_side, quantity=requested)
    return {
        "complete": fill.complete,
        "quantity": fill.filled_quantity,
        "requested_quantity": requested,
        "unfilled_quantity": fill.unfilled_quantity,
        "price": fill.vwap,
        "quote_usd": fill.filled_quantity * fill.vwap,
        "levels_consumed": fill.levels_consumed,
    }


def first_book(
    books: Sequence[Record], start_ms: int, maximum_delay_ms: int
) -> Record | None:
    """Return the first causal book within the allowed observation delay."""
    times = tuple(book_time(row) for row in books)
    index = bisect_left(times, start_ms)
    if index == len(books) or times[index] - start_ms > maximum_delay_ms:
        return None
    return books[index]


def post_entry_books(
    books: Sequence[Record], entry_time_ms: int, deadline_ms: int
) -> tuple[Record, ...]:
    """Return books observed strictly after entry through the deadline."""
    return tuple(row for row in books if entry_time_ms < book_time(row) <= deadline_ms)


def first_stop_book(
    books: Sequence[Record], *, side: str, stop_price: float
) -> Record | None:
    """Return the first recorded BBO crossing of the protective stop."""
    return next((row for row in books if _stop_crossed(row, side, stop_price)), None)


def book_time(row: Record) -> int:
    """Return one exact book receipt timestamp."""
    return nonnegative_int(payload(row).get("recv_ts_ms"), "book receive time")


def latest_book_time(books: Sequence[Record]) -> int:
    """Return the last book time, or -1 when no book exists."""
    return book_time(books[-1]) if books else -1


def protective_stop_price(side: str, entry_price: float, stop_bps: float) -> float:
    """Return the fixed-basis-point stop anchored to actual entry VWAP."""
    if side == "long":
        return entry_price * (1.0 - stop_bps / 10_000.0)
    if side == "short":
        return entry_price * (1.0 + stop_bps / 10_000.0)
    raise ValueError("eligible exact-depth candidate requires long or short")


def directional_return_bps(side: str, entry_price: float, exit_price: float) -> float:
    """Return exact long or short price return in basis points."""
    if side == "long":
        return (exit_price / entry_price - 1.0) * 10_000.0
    if side == "short":
        return (entry_price / exit_price - 1.0) * 10_000.0
    raise ValueError("eligible exact-depth candidate requires long or short")


def _stop_crossed(book: Record, side: str, stop_price: float) -> bool:
    values = payload(book)
    bids = _levels(values.get("bids"), "sell")
    asks = _levels(values.get("asks"), "buy")
    return (
        bids[0].price <= stop_price if side == "long" else asks[0].price >= stop_price
    )


def _levels(value: object, side: str) -> tuple[DepthLevel, ...]:
    rows = _records(value, f"book {side} levels")
    levels = tuple(
        DepthLevel(
            _positive(row.get("price"), "level price"),
            _positive(row.get("size"), "level size"),
        )
        for row in rows
    )
    prices = tuple(level.price for level in levels)
    invalid = (
        side == "buy" and any(left >= right for left, right in zip(prices, prices[1:]))
    ) or (
        side == "sell" and any(left <= right for left, right in zip(prices, prices[1:]))
    )
    if invalid:
        raise ValueError(f"book {side} levels are not strictly ordered")
    return levels


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(mapping(row, label) for row in value)


def _positive(value: object, label: str) -> float:
    result = number(value, label)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
