"""Causal BBO maker-entry reconstruction for Market Cipher signals."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import pandas as pd
from pandas.api.types import is_list_like

Direction = Literal["long", "short"]
EntryStatus = Literal["filled", "unfilled", "missing_book"]

_BOOK_COLUMNS = {"ts_exchange_ms", "best_bid", "best_ask", "bids", "asks"}
_TRADE_COLUMNS = {"ts_exchange_ms", "aggressor_side", "price", "size"}
_MINUTE_MS = 60_000


@dataclass(frozen=True)
class MakerEntryConfig:
    """Frozen delay and queue-depletion assumptions for one maker order."""

    entry_ttl_seconds: int = 300
    maximum_book_delay_ms: int = 1_000

    def __post_init__(self) -> None:
        """Reject non-positive horizons and boolean-shaped integers."""
        for name, value in (
            ("entry_ttl_seconds", self.entry_ttl_seconds),
            ("maximum_book_delay_ms", self.maximum_book_delay_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class MakerEntryRequest:
    """One accepted baseline trade whose entry is being reconstructed."""

    decision_time_ms: int
    direction: Direction
    quantity: float
    original_entry_price: float
    stop_anchor: float
    signal_score: float

    def __post_init__(self) -> None:
        """Reject malformed identity, direction, prices, size, and score."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
        ):
            raise ValueError("decision_time_ms must be a nonnegative integer")
        if self.direction not in {"long", "short"}:
            raise ValueError("maker direction must be long or short")
        values = (
            self.quantity,
            self.original_entry_price,
            self.stop_anchor,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("maker request prices and quantity must be positive")
        if not math.isfinite(self.signal_score):
            raise ValueError("maker request signal score must be finite")


@dataclass(frozen=True)
class MakerEntryOutcome:
    """Observed queue, public-volume, fill, and lifecycle-start evidence."""

    status: EntryStatus
    book_time_ms: int | None
    limit_price: float | None
    displayed_queue: float
    required_volume: float
    observed_trade_volume: float
    fill_time_ms: int | None
    wait_seconds: float | None
    entry_improvement_bps: float | None
    lifecycle_start_time_ms: int | None
    lifecycle_gap_seconds: float | None


def reconstruct_maker_entry(
    request: MakerEntryRequest,
    books: pd.DataFrame,
    trades: pd.DataFrame,
    config: MakerEntryConfig = MakerEntryConfig(),
) -> MakerEntryOutcome:
    """Reconstruct one post-only fill behind displayed BBO queue."""
    book = _first_usable_book(books, request, config)
    if book is None:
        return _missing_book()
    short = request.direction == "short"
    limit = float(book["best_ask" if short else "best_bid"])
    levels = book["asks" if short else "bids"]
    queue = _displayed_queue(levels, limit)
    book_time = int(book["ts_exchange_ms"])
    eligible = _eligible_trades(trades, request.direction, limit, book_time, config)
    required = queue + request.quantity
    fill_time, observed = _fill_time(eligible, required)
    if fill_time is None:
        return MakerEntryOutcome(
            "unfilled",
            book_time,
            limit,
            queue,
            required,
            observed,
            None,
            None,
            None,
            None,
            None,
        )
    lifecycle_start = (fill_time // _MINUTE_MS + 1) * _MINUTE_MS
    return MakerEntryOutcome(
        "filled",
        book_time,
        limit,
        queue,
        required,
        observed,
        fill_time,
        (fill_time - book_time) / 1_000.0,
        _entry_improvement_bps(request, limit),
        lifecycle_start,
        (lifecycle_start - fill_time) / 1_000.0,
    )


def build_maker_replay_signal(
    request: MakerEntryRequest,
    outcome: MakerEntryOutcome,
    *,
    candidate: str,
) -> dict[str, object]:
    """Convert one reconstructed fill into an exact-price replay signal."""
    if (
        outcome.status != "filled"
        or outcome.lifecycle_start_time_ms is None
        or outcome.limit_price is None
    ):
        raise ValueError("maker replay signal requires a filled maker outcome")
    if not candidate.strip():
        raise ValueError("maker replay candidate must be non-empty")
    signal_ms = outcome.lifecycle_start_time_ms - _MINUTE_MS
    return {
        "signal_time_utc": pd.Timestamp(signal_ms, unit="ms", tz="UTC"),
        "symbol": "BTC",
        "candidate": candidate,
        "side": request.direction,
        "score": request.signal_score,
        "stop_anchor": request.stop_anchor,
        "eligible": True,
        "entry_price_override": outcome.limit_price,
    }


def _first_usable_book(
    books: pd.DataFrame,
    request: MakerEntryRequest,
    config: MakerEntryConfig,
) -> pd.Series | None:
    if books.empty:
        return None
    missing = sorted(_BOOK_COLUMNS.difference(books.columns))
    if missing:
        raise ValueError(f"maker entry books missing columns: {missing}")
    ordered = books.sort_values("ts_exchange_ms")
    future = ordered.loc[ordered["ts_exchange_ms"].ge(request.decision_time_ms)]
    if future.empty:
        return None
    first = future.iloc[0]
    delay = int(first["ts_exchange_ms"]) - request.decision_time_ms
    return first if delay <= config.maximum_book_delay_ms else None


def _eligible_trades(
    trades: pd.DataFrame,
    direction: Direction,
    limit: float,
    book_time_ms: int,
    config: MakerEntryConfig,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=sorted(_TRADE_COLUMNS))
    missing = sorted(_TRADE_COLUMNS.difference(trades.columns))
    if missing:
        raise ValueError(f"maker entry trades missing columns: {missing}")
    end_ms = book_time_ms + config.entry_ttl_seconds * 1_000
    window = trades["ts_exchange_ms"].between(book_time_ms, end_ms)
    aggressor = "buy" if direction == "short" else "sell"
    crossed = (
        trades["price"].ge(limit) if direction == "short" else trades["price"].le(limit)
    )
    return trades.loc[
        window & trades["aggressor_side"].eq(aggressor) & crossed
    ].sort_values("ts_exchange_ms")


def _fill_time(trades: pd.DataFrame, required: float) -> tuple[int | None, float]:
    observed = 0.0
    for row in trades.itertuples(index=False):
        size = float(getattr(row, "size"))
        if not math.isfinite(size) or size < 0.0:
            raise ValueError("maker entry trade size must be finite and nonnegative")
        observed += size
        if observed >= required:
            return int(getattr(row, "ts_exchange_ms")), observed
    return None, observed


def _displayed_queue(levels: object, limit: float) -> float:
    if isinstance(levels, (str, bytes, dict)) or not is_list_like(levels):
        raise ValueError("maker entry BBO levels must be a list")
    for level in levels:
        if isinstance(level, dict) and float(level.get("px", math.nan)) == limit:
            size = float(level.get("sz", math.nan))
            if math.isfinite(size) and size >= 0.0:
                return size
    raise ValueError("maker entry limit is absent from displayed BBO levels")


def _entry_improvement_bps(request: MakerEntryRequest, limit: float) -> float:
    delta = (
        limit - request.original_entry_price
        if request.direction == "short"
        else request.original_entry_price - limit
    )
    return delta / request.original_entry_price * 10_000.0


def _missing_book() -> MakerEntryOutcome:
    return MakerEntryOutcome(
        "missing_book",
        None,
        None,
        0.0,
        0.0,
        0.0,
        None,
        None,
        None,
        None,
        None,
    )
