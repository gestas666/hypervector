"""Recent live-ledger visible-depth evidence at a proposed notional."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import ceil, floor, isfinite

from hypervector.research.market_depth_fill import DepthLevel, walk_market_order

Record = Mapping[str, object]


@dataclass(frozen=True)
class _Book:
    """One validated asset-bound live book observation."""

    timestamp_ms: int
    mid_price: float
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]


def build_recent_liquidity_profile(
    records: Sequence[Record],
    *,
    run_id: str,
    symbol: str,
    profile_id: str,
    profile_fingerprint: str,
    notional_usd: float,
    maximum_snapshots: int = 240,
) -> dict[str, object]:
    """Measure finite visible-depth cost from a bounded selected-run suffix."""
    selected_run = _text(run_id, "run_id")
    selected_symbol = _text(symbol, "symbol")
    selected_profile = _text(profile_id, "profile_id")
    selected_fingerprint = _text(profile_fingerprint, "profile_fingerprint")
    notional = _positive(notional_usd, "notional_usd")
    limit = _positive_integer(maximum_snapshots, "maximum_snapshots")
    books = _selected_books(
        records,
        run_id=selected_run,
        symbol=selected_symbol,
        profile_id=selected_profile,
        profile_fingerprint=selected_fingerprint,
    )[-limit:]
    if not books:
        raise ValueError(f"selected run has no {selected_symbol} book observations")
    timestamps = tuple(book.timestamp_ms for book in books)
    if timestamps != tuple(sorted(set(timestamps))):
        raise ValueError("selected book timestamps must be unique and increasing")
    costs = tuple(_visible_cost(book, notional) for book in books)
    buys = [row[0] for row in costs if row[0] is not None]
    sells = [row[1] for row in costs if row[1] is not None]
    round_trips = [
        buy + sell for buy, sell in costs if buy is not None and sell is not None
    ]
    count = len(books)
    return {
        "schema_version": 1,
        "mode": "cohort_recent_visible_depth_v1",
        "contract": _contract(),
        "run_id": selected_run,
        "symbol": selected_symbol,
        "profile_id": selected_profile,
        "profile_fingerprint": selected_fingerprint,
        "notional_usd": notional,
        "snapshot_count": count,
        "window_start_timestamp_ms": timestamps[0],
        "window_end_timestamp_ms": timestamps[-1],
        "buy_complete_rate": len(buys) / count,
        "sell_complete_rate": len(sells) / count,
        "both_complete_rate": len(round_trips) / count,
        "buy_visible_cost_bps": _distribution(buys),
        "sell_visible_cost_bps": _distribution(sells),
        "round_trip_visible_cost_bps": _distribution(round_trips),
        "limitations": _limitations(),
    }


def _selected_books(
    records: Sequence[Record],
    *,
    run_id: str,
    symbol: str,
    profile_id: str,
    profile_fingerprint: str,
) -> tuple[_Book, ...]:
    """Validate the exact run/profile binding before parsing its books."""
    selected = tuple(row for row in records if row.get("run_id") == run_id)
    identities = tuple(
        row for row in selected if row.get("event_type") == "configuration_identity"
    )
    if not identities:
        raise ValueError("selected run has no configuration identity")
    for identity in identities:
        payload = _mapping(identity.get("payload"), "configuration identity payload")
        if payload.get("symbol") != symbol:
            raise ValueError("configuration identity symbol does not match request")
        _require_profile(identity, profile_id, profile_fingerprint)
    book_rows = tuple(
        row for row in selected if row.get("event_type") == "book_observation"
    )
    for row in book_rows:
        _require_profile(row, profile_id, profile_fingerprint)
    return tuple(_book(row) for row in book_rows)


def _require_profile(record: Record, profile_id: str, fingerprint: str) -> None:
    """Require one exact asset profile envelope."""
    if (
        record.get("profile_id") != profile_id
        or record.get("profile_fingerprint") != fingerprint
    ):
        raise ValueError("selected ledger profile identity does not match request")


def _book(record: Record) -> _Book:
    payload = _mapping(record.get("payload"), "book payload")
    return _Book(
        timestamp_ms=_nonnegative_integer(
            payload.get("recv_ts_ms"), "book receive timestamp"
        ),
        mid_price=_positive(payload.get("mid_px"), "book midpoint"),
        bids=_levels(payload.get("bids"), "bids"),
        asks=_levels(payload.get("asks"), "asks"),
    )


def _levels(value: object, label: str) -> tuple[DepthLevel, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must contain visible depth")
    levels: list[DepthLevel] = []
    for raw in value:
        row = _mapping(raw, f"{label} level")
        levels.append(
            DepthLevel(
                price=_positive(row.get("price"), f"{label} price"),
                size=_positive(row.get("size"), f"{label} size"),
            )
        )
    return tuple(levels)


def _visible_cost(
    book: _Book,
    notional_usd: float,
) -> tuple[float | None, float | None]:
    quantity = notional_usd / book.mid_price
    buy = walk_market_order(book.asks, side="buy", quantity=quantity)
    sell = walk_market_order(book.bids, side="sell", quantity=quantity)
    buy_cost = (buy.vwap / book.mid_price - 1.0) * 10_000.0 if buy.complete else None
    sell_cost = (1.0 - sell.vwap / book.mid_price) * 10_000.0 if sell.complete else None
    return buy_cost, sell_cost


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(value for value in values if isfinite(value))
    if not ordered:
        return {"count": 0, "p50": None, "p90": None, "p99": None}
    return {
        "count": len(ordered),
        "p50": _quantile(ordered, 0.50),
        "p90": _quantile(ordered, 0.90),
        "p99": _quantile(ordered, 0.99),
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "automatic_sizing_change": False,
    }


def _limitations() -> list[str]:
    return [
        "visible_l2_only_no_queue_or_fill_probability",
        "recent_books_not_conditioned_on_strategy_entry_timestamps",
        "public_depth_can_cancel_before_a_live_ioc_arrives",
        "p99_is_an_empirical_quantile_not_a_worst_case_bound",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return number


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()
