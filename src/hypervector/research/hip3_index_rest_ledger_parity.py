"""Exact receipt-causal reconciliation of HIP-3 observer book decisions."""

from __future__ import annotations

import math
from typing import NamedTuple, cast

Record = dict[str, object]
_BAR_MS = 900_000
_MAXIMUM_AGE_MS = 15_000
_TOLERANCE = 1e-12
_SOURCE = "hyperliquid_mainnet_l2_rest"


class _Book(NamedTuple):
    exchange_ms: int
    receipt_ms: int
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]

    @property
    def market_identity(self) -> tuple[object, ...]:
        return self.exchange_ms, self.bids, self.asks

    @property
    def imbalance_10(self) -> float:
        bid = sum(level[1] for level in self.bids)
        ask = sum(level[1] for level in self.asks)
        return (bid - ask) / (bid + ask)


def reconcile_observer_rest_ledger(
    rows: list[Record], observers: list[Record], symbol: str
) -> None:
    """Fail unless every frozen observer decision matches its raw ledger prefix."""
    parsed = tuple(_book(row, symbol) for row in rows)
    _require_receipt_order(parsed)
    for decision in observers:
        if not _decision_matches(decision, parsed):
            raise ValueError("observer decision differs from REST ledger")


def _decision_matches(decision: Record, books: tuple[_Book, ...]) -> bool:
    boundary = _integer(decision, "decision_time_ms")
    observed = _integer(decision, "observed_at_ms")
    bar_open = boundary - _BAR_MS
    available = tuple(book for book in books if book.receipt_ms <= observed)
    scan_complete = any(book.receipt_ms < bar_open for book in available)
    selected = _canonical(
        book for book in available if bar_open <= book.exchange_ms < boundary
    )
    last = selected[-1] if selected else None
    age = None if last is None else boundary - last.exchange_ms
    fresh = bool(
        scan_complete
        and len(selected) >= 2
        and age is not None
        and 0 <= age <= _MAXIMUM_AGE_MS
    )
    effective = 0.0 if last is None or not fresh else last.imbalance_10
    exact = _exact_fields(decision, selected, last, age, scan_complete, fresh)
    return exact and math.isclose(
        _number(decision, "decision_imbalance_10"),
        effective,
        rel_tol=0.0,
        abs_tol=_TOLERANCE,
    )


def _exact_fields(
    decision: Record,
    books: tuple[_Book, ...],
    last: _Book | None,
    age: int | None,
    scan_complete: bool,
    fresh: bool,
) -> bool:
    exchange = None if last is None else last.exchange_ms
    receipt = None if last is None else last.receipt_ms
    return bool(
        decision.get("pressure_source") == _SOURCE
        and _integer(decision, "pressure_snapshot_count") == len(books)
        and _optional_integer(decision, "pressure_exchange_ts_ms") == exchange
        and _optional_integer(decision, "pressure_recv_ts_ms") == receipt
        and _optional_integer(decision, "pressure_end_boundary_age_ms") == age
        and decision.get("pressure_scan_complete") is scan_complete
        and decision.get("pressure_fresh") is fresh
        and decision.get("pressure_status") == _status(scan_complete, len(books), age)
    )


def _book(row: Record, symbol: str) -> _Book:
    if row.get("event_type") != "book_observation":
        raise ValueError("REST ledger contains a non-book row")
    payload = _mapping(row.get("payload"), "REST book payload")
    if payload.get("symbol") != symbol or payload.get("source") != _SOURCE:
        raise ValueError("REST book identity is invalid")
    book = _Book(
        _integer(payload, "exchange_ts_ms"),
        _integer(payload, "recv_ts_ms"),
        _levels(payload.get("bids"), "REST bids"),
        _levels(payload.get("asks"), "REST asks"),
    )
    if book.receipt_ms < book.exchange_ms:
        raise ValueError("REST receipt timestamp precedes exchange time")
    return book


def _levels(value: object, label: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) < 10:
        raise ValueError(f"{label} must contain at least ten levels")
    levels = tuple(_level(row, label) for row in value[:10])
    if sum(level[1] for level in levels) <= 0.0:
        raise ValueError(f"{label} must contain positive depth")
    return levels


def _level(value: object, label: str) -> tuple[float, float]:
    row = _mapping(value, label)
    price = _positive(row.get("price"), f"{label} price")
    size = _positive(row.get("size"), f"{label} size")
    return price, size


def _canonical(values: object) -> tuple[_Book, ...]:
    books: dict[int, _Book] = {}
    for book in values:
        if not isinstance(book, _Book):
            raise TypeError("REST canonical values must be books")
        prior = books.get(book.exchange_ms)
        if prior is not None and prior.market_identity != book.market_identity:
            raise ValueError("REST ledger has conflicting exchange timestamps")
        if prior is None or book.receipt_ms < prior.receipt_ms:
            books[book.exchange_ms] = book
    return tuple(books[key] for key in sorted(books))


def _require_receipt_order(books: tuple[_Book, ...]) -> None:
    receipts = [book.receipt_ms for book in books]
    if receipts != sorted(receipts):
        raise ValueError("REST ledger receipt chronology regressed")


def _status(complete: bool, count: int, age: int | None) -> str:
    if not complete:
        return "truncated_ledger_tail"
    if count == 0:
        return "no_snapshots"
    if count < 2:
        return "insufficient_snapshots"
    if age is None or age > _MAXIMUM_AGE_MS:
        return "stale"
    return "fresh"


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(Record, value)


def _integer(value: Record, key: str) -> int:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, int):
        raise ValueError(f"{key} must be an integer")
    return selected


def _optional_integer(value: Record, key: str) -> int | None:
    selected = value.get(key)
    return None if selected is None else _integer(value, key)


def _number(value: Record, key: str) -> float:
    selected = value.get(key)
    if isinstance(selected, bool) or not isinstance(selected, (int, float)):
        raise ValueError(f"{key} must be numeric")
    number = float(selected)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number


def _positive(value: object, label: str) -> float:
    number = _number({"value": value}, "value")
    if number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number
