"""Exact visible-depth diagnostics for observer replay entry attempts."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    nonnegative_int,
    number,
    payload,
    text,
)
from hypervector.research.market_depth_fill import (
    DepthLevel,
    depth_levels_from_records,
    walk_market_order,
)

Record = Mapping[str, object]


def build_attempt_entry_depth_diagnostics(
    replay: Record,
    asset_records: Sequence[Record],
) -> dict[str, object]:
    """Measure recorded multi-level entry capacity without claiming fills."""
    contract = _mapping(replay.get("contract"), "replay contract")
    symbol = text(contract.get("symbol"), "replay symbol")
    notional = _positive(contract.get("notional_usd"), "replay notional")
    delay = nonnegative_int(
        contract.get("maximum_entry_delay_ms"), "maximum entry delay"
    )
    books = _books(asset_records, symbol)
    attempts = _records(replay.get("attempts"), "replay attempts")
    rows = tuple(_attempt(row, books, notional, delay, symbol) for row in attempts)
    return {
        "schema_version": 1,
        "mode": "observer_entry_visible_depth_diagnostic",
        "symbol": symbol,
        "notional_usd": notional,
        "attempt_count": len(rows),
        "visible_depth_complete_count": sum(
            row.get("visible_depth_complete") is True for row in rows
        ),
        "attempts": rows,
        "fills_claimed": False,
        "execution_authority": "none",
        "limitations": [
            "visible_depth_can_cancel_before_a_live_ioc_arrives",
            "recorded_books_do_not_prove_a_fill_between_observations",
        ],
    }


def _attempt(
    attempt: Record,
    books: Sequence[Record],
    notional: float,
    delay: int,
    symbol: str,
) -> dict[str, object]:
    if attempt.get("symbol") != symbol:
        raise ValueError("replay attempt symbol does not match contract")
    available = nonnegative_int(attempt.get("available_time_ms"), "available time")
    base = {
        "decision_time_ms": nonnegative_int(
            attempt.get("decision_time_ms"), "decision time"
        ),
        "available_time_ms": available,
        "side": text(attempt.get("side"), "attempt side"),
        "replay_status": text(attempt.get("status"), "replay status"),
    }
    book = _first_book(books, available, delay)
    if book is None:
        return base | {"status": "entry_book_missing"}
    return base | _walk(book, base["side"], notional)


def _walk(book: Record, side: object, notional: float) -> dict[str, object]:
    values = payload(book)
    mid = _positive(values.get("mid_px"), "book midpoint")
    quantity = notional / mid
    if side == "long":
        levels, market_side = values.get("asks"), "buy"
    elif side == "short":
        levels, market_side = values.get("bids"), "sell"
    else:
        raise ValueError("attempt side must be long or short")
    depth = _depth_levels(levels, market_side)
    fill = walk_market_order(depth, side=market_side, quantity=quantity)
    cost = (
        (fill.vwap / mid - 1.0) * 10_000.0
        if market_side == "buy"
        else (1.0 - fill.vwap / mid) * 10_000.0
    )
    return {
        "status": "measured",
        "book_time_ms": nonnegative_int(values.get("recv_ts_ms"), "book time"),
        "requested_quantity": quantity,
        "top_level_complete": depth[0].size + 1e-12 >= quantity,
        "visible_depth_complete": fill.complete,
        "filled_quantity": fill.filled_quantity,
        "levels_consumed": fill.levels_consumed,
        "visible_vwap": fill.vwap,
        "visible_cost_bps": cost,
    }


def _books(records: Sequence[Record], symbol: str) -> tuple[Record, ...]:
    rows = tuple(event_rows(records, "book_observation"))
    for row in rows:
        if payload(row).get("symbol") != symbol:
            raise ValueError("asset book symbol does not match replay contract")
    ordered = tuple(sorted(rows, key=lambda row: _book_time(row)))
    times = tuple(_book_time(row) for row in ordered)
    if len(set(times)) != len(times):
        raise ValueError("asset book receive timestamps must be unique")
    return ordered


def _first_book(
    books: Sequence[Record], available: int, maximum_delay: int
) -> Record | None:
    times = [_book_time(row) for row in books]
    index = bisect_left(times, available)
    if index >= len(books) or times[index] - available > maximum_delay:
        return None
    return books[index]


def _book_time(row: Record) -> int:
    return nonnegative_int(payload(row).get("recv_ts_ms"), "book receive time")


def _depth_levels(value: object, side: str) -> tuple[DepthLevel, ...]:
    rows = _records(value, f"book {side} levels")
    normalized = [
        {
            "px": _positive(row.get("price"), "level price"),
            "sz": _positive(row.get("size"), "level size"),
        }
        for row in rows
    ]
    return depth_levels_from_records(normalized, label=side)


def _records(value: object, label: str) -> tuple[Record, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return tuple(_mapping(row, label) for row in value)


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must contain objects")
    return value


def _positive(value: object, label: str) -> float:
    parsed = number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"{label} must be positive")
    return parsed
