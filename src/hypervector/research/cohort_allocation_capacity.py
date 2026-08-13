"""Bounded visible-depth capacity evidence for one HYPE allocation trial."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import statistics

from hypervector.research.market_depth_fill import (
    DepthLevel,
    MarketSide,
    walk_market_order,
)

Record = Mapping[str, object]

_SYMBOL = "HYPE"
_MAX_SNAPSHOTS = 240


@dataclass(frozen=True)
class _Book:
    recv_timestamp_ms: int
    mid_price: float
    bids: tuple[DepthLevel, ...]
    asks: tuple[DepthLevel, ...]


def allocation_capacity_available(
    records: Sequence[Record],
    *,
    run_id: str,
) -> bool:
    """Return whether the selected run contains at least one full-depth book."""
    return any(
        row.get("run_id") == run_id and row.get("event_type") == "book_observation"
        for row in records
    )


def build_allocation_capacity(
    records: Sequence[Record],
    *,
    run_id: str,
    current_notional_usd: float,
    candidate_notional_usd: float,
) -> dict[str, object]:
    """Measure candidate IOC capacity from recent selected-run public L2 books."""
    current = _positive(current_notional_usd, "current notional")
    candidate = _positive(candidate_notional_usd, "candidate notional")
    if candidate < current:
        raise ValueError("candidate notional must not be below current notional")
    books = _selected_books(records, run_id)
    timestamps = [book.recv_timestamp_ms for book in books]
    if timestamps != sorted(set(timestamps)):
        raise ValueError("selected book timestamps must be unique and increasing")
    return {
        "status": "observed",
        "symbol": _SYMBOL,
        "snapshot_count": len(books),
        "current_notional_usd": current,
        "candidate_notional_usd": candidate,
        "window_start_timestamp_ms": timestamps[0],
        "window_end_timestamp_ms": timestamps[-1],
        "contract": _contract(),
        "by_side": {
            "long": _side_capacity(books, candidate, "buy"),
            "short": _side_capacity(books, candidate, "sell"),
        },
        "limitations": _limitations(),
    }


def _selected_books(records: Sequence[Record], run_id: str) -> tuple[_Book, ...]:
    selected = [
        _book(row)
        for row in records
        if row.get("run_id") == run_id and row.get("event_type") == "book_observation"
    ]
    if not selected:
        raise ValueError("selected run has no HYPE book observations")
    return tuple(selected[-_MAX_SNAPSHOTS:])


def _book(record: Record) -> _Book:
    values = _mapping(record.get("payload"), "book payload")
    return _Book(
        recv_timestamp_ms=_nonnegative_int(
            values.get("recv_ts_ms"), "book receive timestamp"
        ),
        mid_price=_positive(values.get("mid_px"), "book midpoint"),
        bids=_levels(values.get("bids"), "bids"),
        asks=_levels(values.get("asks"), "asks"),
    )


def _levels(value: object, label: str) -> tuple[DepthLevel, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must contain visible depth")
    levels = []
    for raw in value:
        row = _mapping(raw, f"{label} level")
        levels.append(
            DepthLevel(
                price=_positive(row.get("price"), f"{label} price"),
                size=_positive(row.get("size"), f"{label} size"),
            )
        )
    return tuple(levels)


def _side_capacity(
    books: Sequence[_Book],
    notional_usd: float,
    side: MarketSide,
) -> dict[str, object]:
    fills = []
    bbo_notionals = []
    for book in books:
        levels = book.asks if side == "buy" else book.bids
        fill = walk_market_order(
            levels,
            side=side,
            quantity=notional_usd / book.mid_price,
        )
        fills.append(fill)
        bbo_notionals.append(levels[0].price * levels[0].size)
    complete = [fill for fill in fills if fill.complete]
    impacts = [fill.impact_bps for fill in complete]
    return {
        "complete_rate": len(complete) / len(fills),
        "bbo_fill_rate": sum(
            fill.complete and fill.levels_consumed == 1 for fill in fills
        )
        / len(fills),
        "median_impact_bps": statistics.median(impacts) if impacts else None,
        "p95_impact_bps": _nearest_rank(impacts, 0.95) if impacts else None,
        "maximum_impact_bps": max(impacts) if impacts else None,
        "minimum_bbo_notional_usd": min(bbo_notionals),
    }


def _nearest_rank(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "fills_assumed": False,
        "promotion_gate": False,
    }


def _limitations() -> list[str]:
    return [
        "public L2 can cancel before a live IOC reaches the venue",
        "rolling books are not conditioned on strategy entry timestamps",
        "observed capacity does not establish signal edge or future slippage",
    ]


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
