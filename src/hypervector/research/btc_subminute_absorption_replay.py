"""Report-only lifecycle replay for BTC subminute absorption signals."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.market_depth_fill import DepthLevel, walk_market_order


_SIGNAL_COLUMNS = frozenset({"event_id", "arm", "symbol", "side", "available_at_utc"})
_BOOK_COLUMNS = frozenset(
    {"ts_exchange_ms", "best_bid", "best_ask", "mid_price", "bids", "asks"}
)
_TRADE_COLUMNS = frozenset({"trade_id", "ts_exchange_ms", "price"})
_TRADE_OUTPUT_COLUMNS = (
    "event_id",
    "arm",
    "scenario",
    "entry_time_ms",
    "exit_time_ms",
    "exit_reason",
    "same_timestamp_ambiguity",
    "entry_price",
    "exit_price",
    "target_price",
    "stop_price",
    "quantity",
    "entry_notional_usd",
    "exit_notional_usd",
    "gross_pnl_usd",
    "fee_usd",
    "funding_usd",
    "net_pnl_usd",
    "gross_return_bps",
    "net_return_bps",
    "exit_fee_rate",
)


@dataclass(frozen=True)
class BtcAbsorptionReplayConfig:
    """One frozen visible-depth and exit-proxy replay scenario."""

    scenario: str = "nominal_midpoint_stop_proxy"
    entry_notional_usd: float = 5_000.0
    entry_latency_ms: int = 500
    maximum_entry_book_delay_ms: int = 5_000
    maximum_exit_book_delay_ms: int = 5_000
    additional_entry_slippage_bps: float = 0.0
    target_bps: float = 60.0
    stop_bps: float = 60.0
    maximum_hold_seconds: int = 86_400
    entry_fee_rate: float = 0.00045
    target_fee_rate: float = 0.00015
    market_exit_fee_rate: float = 0.00045
    stop_trigger_proxy: str = "midpoint"

    def __post_init__(self) -> None:
        if self.stop_trigger_proxy not in {"midpoint", "public_trade"}:
            raise ValueError(
                "BTC absorption stop trigger must be midpoint or public_trade"
            )
        integer_values = (
            self.entry_latency_ms,
            self.maximum_entry_book_delay_ms,
            self.maximum_exit_book_delay_ms,
            self.maximum_hold_seconds,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integer_values):
            raise ValueError("BTC absorption replay durations must be positive")
        numeric = (
            self.entry_notional_usd,
            self.target_bps,
            self.stop_bps,
            self.entry_fee_rate,
            self.target_fee_rate,
            self.market_exit_fee_rate,
        )
        if not all(math.isfinite(value) and value > 0.0 for value in numeric):
            raise ValueError("BTC absorption economic values must be positive")
        slip = self.additional_entry_slippage_bps
        if not math.isfinite(slip) or slip < 0.0:
            raise ValueError("BTC absorption entry slippage must be nonnegative")


@dataclass(frozen=True)
class BtcAbsorptionReplayReport:
    """Resolved trades and mutually exclusive attempt rejections."""

    trades: pd.DataFrame
    rejections: dict[str, int]
    attempted_signals: int
    execution_authority: str = "none"
    orders_attempted: bool = False


@dataclass(frozen=True)
class _Entry:
    time_ms: int
    price: float
    quantity: float
    notional: float


@dataclass(frozen=True)
class _ExitEvent:
    time_ms: int
    priority: int
    reason: str
    book_index: int | None


def replay_btc_absorption_signals(
    signals: pd.DataFrame,
    books: pd.DataFrame,
    public_trades: pd.DataFrame,
    funding: pd.Series,
    config: BtcAbsorptionReplayConfig | None = None,
) -> BtcAbsorptionReplayReport:
    """Replay chronological long signals with one BTC position at a time."""
    cfg = config or BtcAbsorptionReplayConfig()
    ordered_signals = _validated_signals(signals)
    ordered_books = _validated_books(books)
    ordered_trades = _validated_trades(public_trades)
    rates = _validated_funding(funding)
    outcomes: list[dict[str, object]] = []
    rejections: dict[str, int] = {}
    occupied_until = -1
    for row in ordered_signals.itertuples(index=False):
        available_ms = int(pd.Timestamp(row.available_at_utc).timestamp() * 1_000)
        if available_ms < occupied_until:
            _increment(rejections, "symbol_position_open")
            continue
        outcome, reason = _simulate(row, ordered_books, ordered_trades, rates, cfg)
        if outcome is None:
            _increment(rejections, reason or "unknown_replay_rejection")
            continue
        outcomes.append(outcome)
        occupied_until = int(outcome["exit_time_ms"]) + 1
    frame = pd.DataFrame(outcomes, columns=_TRADE_OUTPUT_COLUMNS)
    return BtcAbsorptionReplayReport(frame, rejections, len(ordered_signals))


def _validated_signals(signals: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_SIGNAL_COLUMNS.difference(signals.columns))
    if missing:
        raise ValueError(f"BTC absorption replay signals missing: {missing}")
    output = signals.copy()
    output["available_at_utc"] = pd.to_datetime(output["available_at_utc"], utc=True)
    if output["event_id"].duplicated().any():
        raise ValueError("BTC absorption replay event identities must be unique")
    if not output["symbol"].eq("BTC").all() or not output["side"].eq("long").all():
        raise ValueError("BTC absorption replay supports BTC long signals only")
    return output.sort_values(["available_at_utc", "event_id"]).reset_index(drop=True)


def _validated_books(books: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_BOOK_COLUMNS.difference(books.columns))
    if missing:
        raise ValueError(f"BTC absorption replay books missing: {missing}")
    output = books.copy().sort_values("ts_exchange_ms").reset_index(drop=True)
    times = output["ts_exchange_ms"]
    numeric = output[["best_bid", "best_ask", "mid_price"]].to_numpy(float)
    if times.duplicated().any() or not times.is_monotonic_increasing:
        raise ValueError("BTC absorption replay book times must be ordered and unique")
    if not np.isfinite(numeric).all() or (numeric <= 0.0).any():
        raise ValueError("BTC absorption replay book prices must be positive")
    if (output["best_bid"] >= output["best_ask"]).any():
        raise ValueError("BTC absorption replay books must not be crossed")
    for row in output.itertuples(index=False):
        _book_levels(row.bids, ask=False)
        _book_levels(row.asks, ask=True)
    return output


def _validated_trades(trades: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_TRADE_COLUMNS.difference(trades.columns))
    if missing:
        raise ValueError(f"BTC absorption replay trades missing: {missing}")
    output = trades.copy().sort_values(["ts_exchange_ms", "trade_id"])
    if output["trade_id"].duplicated().any():
        raise ValueError("BTC absorption public trades must be deduplicated")
    if not output.empty:
        values = output[["ts_exchange_ms", "price"]].to_numpy(float)
        if not np.isfinite(values).all() or (values[:, 1] <= 0.0).any():
            raise ValueError("BTC absorption public trades are invalid")
    return output.reset_index(drop=True)


def _validated_funding(funding: pd.Series) -> pd.Series:
    if not isinstance(funding.index, pd.DatetimeIndex) or funding.index.tz is None:
        raise ValueError("BTC absorption funding requires aware timestamps")
    if funding.index.has_duplicates or not funding.index.is_monotonic_increasing:
        raise ValueError("BTC absorption funding timestamps must be unique and ordered")
    values = funding.to_numpy(float)
    if not np.isfinite(values).all():
        raise ValueError("BTC absorption funding rates must be finite")
    output = funding.copy()
    output.index = output.index.tz_convert("UTC")
    return output.astype(float)


def _simulate(
    signal: object,
    books: pd.DataFrame,
    trades: pd.DataFrame,
    funding: pd.Series,
    config: BtcAbsorptionReplayConfig,
) -> tuple[dict[str, object] | None, str | None]:
    available = int(
        pd.Timestamp(getattr(signal, "available_at_utc")).timestamp() * 1_000
    )
    entry, reason = _entry(books, available, config)
    if entry is None:
        return None, reason
    deadline = entry.time_ms + config.maximum_hold_seconds * 1_000
    target = entry.price * (1.0 + config.target_bps / 10_000.0)
    stop = entry.price * (1.0 - config.stop_bps / 10_000.0)
    event, ambiguous = _exit_event(books, trades, entry, deadline, target, stop, config)
    if event is None:
        return None, "outcome_path_incomplete"
    exit_terms, reason = _exit_terms(books, entry, event, target, config)
    if exit_terms is None:
        return None, reason
    exit_time, exit_price, exit_fee_rate = exit_terms
    funding_cash = _funding_cash(books, funding, entry, exit_time, config)
    if funding_cash is None:
        return None, "funding_book_unavailable"
    return _trade_record(
        signal,
        entry,
        exit_time,
        exit_price,
        exit_fee_rate,
        target,
        stop,
        event,
        ambiguous,
        funding_cash,
        config,
    ), None


def _entry(
    books: pd.DataFrame,
    available_ms: int,
    config: BtcAbsorptionReplayConfig,
) -> tuple[_Entry | None, str | None]:
    requested = available_ms + config.entry_latency_ms
    index = _first_index(books, requested, config.maximum_entry_book_delay_ms)
    if index is None:
        return None, "entry_book_unavailable"
    row = books.iloc[index]
    levels = _book_levels(row["asks"], ask=True)
    quantity = config.entry_notional_usd / levels[0].price
    fill = walk_market_order(levels, side="buy", quantity=quantity)
    if not fill.complete:
        return None, "entry_visible_depth_incomplete"
    price = fill.vwap * (1.0 + config.additional_entry_slippage_bps / 10_000.0)
    return _Entry(int(row["ts_exchange_ms"]), price, quantity, price * quantity), None


def _exit_event(
    books: pd.DataFrame,
    trades: pd.DataFrame,
    entry: _Entry,
    deadline: int,
    target: float,
    stop: float,
    config: BtcAbsorptionReplayConfig,
) -> tuple[_ExitEvent | None, bool]:
    target_event = _first_book_event(
        books, entry.time_ms, deadline, "best_bid", target, True
    )
    stop_event = (
        _first_book_event(books, entry.time_ms, deadline, "mid_price", stop, False)
        if config.stop_trigger_proxy == "midpoint"
        else _first_trade_stop(trades, entry.time_ms, deadline, stop)
    )
    deadline_index = _first_index(books, deadline, config.maximum_exit_book_delay_ms)
    events = [event for event in (stop_event, target_event) if event is not None]
    if deadline_index is not None:
        events.append(_ExitEvent(deadline, 2, "maximum_hold", deadline_index))
    if not events:
        return None, False
    selected = min(events, key=lambda event: (event.time_ms, event.priority))
    ambiguous = bool(
        stop_event and target_event and stop_event.time_ms == target_event.time_ms
    )
    return selected, ambiguous


def _first_book_event(
    books: pd.DataFrame,
    entry_ms: int,
    deadline: int,
    column: str,
    threshold: float,
    greater: bool,
) -> _ExitEvent | None:
    selected = books.loc[
        (books["ts_exchange_ms"] > entry_ms) & (books["ts_exchange_ms"] <= deadline)
    ]
    crossed = (
        selected[column].ge(threshold) if greater else selected[column].le(threshold)
    )
    if not crossed.any():
        return None
    index = int(crossed[crossed].index[0])
    reason = "fixed_target" if greater else "protective_stop_proxy"
    return _ExitEvent(
        int(books.loc[index, "ts_exchange_ms"]), 1 if greater else 0, reason, index
    )


def _first_trade_stop(
    trades: pd.DataFrame,
    entry_ms: int,
    deadline: int,
    stop: float,
) -> _ExitEvent | None:
    selected = trades.loc[
        (trades["ts_exchange_ms"] > entry_ms)
        & (trades["ts_exchange_ms"] <= deadline)
        & (trades["price"] <= stop)
    ]
    if selected.empty:
        return None
    return _ExitEvent(
        int(selected.iloc[0]["ts_exchange_ms"]), 0, "protective_stop_proxy", None
    )


def _exit_terms(
    books: pd.DataFrame,
    entry: _Entry,
    event: _ExitEvent,
    target: float,
    config: BtcAbsorptionReplayConfig,
) -> tuple[tuple[int, float, float] | None, str | None]:
    if event.reason == "fixed_target":
        return (event.time_ms, target, config.target_fee_rate), None
    index = event.book_index
    if index is None:
        index = _first_index(books, event.time_ms, config.maximum_exit_book_delay_ms)
    if index is None:
        return None, "exit_book_unavailable"
    row = books.iloc[index]
    fill = walk_market_order(
        _book_levels(row["bids"], ask=False), side="sell", quantity=entry.quantity
    )
    if not fill.complete:
        return None, "exit_visible_depth_incomplete"
    return (int(row["ts_exchange_ms"]), fill.vwap, config.market_exit_fee_rate), None


def _funding_cash(
    books: pd.DataFrame,
    funding: pd.Series,
    entry: _Entry,
    exit_ms: int,
    config: BtcAbsorptionReplayConfig,
) -> float | None:
    total = 0.0
    for timestamp, rate in funding.items():
        settlement_ms = int(pd.Timestamp(timestamp).timestamp() * 1_000)
        if not entry.time_ms < settlement_ms <= exit_ms:
            continue
        index = _first_index(books, settlement_ms, config.maximum_exit_book_delay_ms)
        if index is None:
            return None
        mark_proxy = float(books.iloc[index]["mid_price"])
        total -= entry.quantity * mark_proxy * float(rate)
    return total


def _trade_record(
    signal: object,
    entry: _Entry,
    exit_time: int,
    exit_price: float,
    exit_fee_rate: float,
    target: float,
    stop: float,
    event: _ExitEvent,
    ambiguous: bool,
    funding: float,
    config: BtcAbsorptionReplayConfig,
) -> dict[str, object]:
    exit_notional = entry.quantity * exit_price
    gross = exit_notional - entry.notional
    fee = entry.notional * config.entry_fee_rate + exit_notional * exit_fee_rate
    net = gross - fee + funding
    return {
        "event_id": str(getattr(signal, "event_id")),
        "arm": str(getattr(signal, "arm")),
        "scenario": config.scenario,
        "entry_time_ms": entry.time_ms,
        "exit_time_ms": exit_time,
        "exit_reason": event.reason,
        "same_timestamp_ambiguity": ambiguous,
        "entry_price": entry.price,
        "exit_price": exit_price,
        "target_price": target,
        "stop_price": stop,
        "quantity": entry.quantity,
        "entry_notional_usd": entry.notional,
        "exit_notional_usd": exit_notional,
        "gross_pnl_usd": gross,
        "fee_usd": fee,
        "funding_usd": funding,
        "net_pnl_usd": net,
        "gross_return_bps": gross / entry.notional * 10_000.0,
        "net_return_bps": net / entry.notional * 10_000.0,
        "exit_fee_rate": exit_fee_rate,
    }


def _first_index(
    books: pd.DataFrame, start_ms: int, maximum_delay_ms: int
) -> int | None:
    times = books["ts_exchange_ms"].tolist()
    position = bisect_left(times, start_ms)
    if position == len(times) or int(times[position]) - start_ms > maximum_delay_ms:
        return None
    return position


def _book_levels(value: object, *, ask: bool) -> tuple[DepthLevel, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("BTC absorption depth levels must be a sequence")
    levels = tuple(_depth_level(row) for row in value)
    if not levels:
        raise ValueError("BTC absorption depth levels must be non-empty")
    prices = tuple(level.price for level in levels)
    invalid = (
        any(left >= right for left, right in zip(prices, prices[1:]))
        if ask
        else any(left <= right for left, right in zip(prices, prices[1:]))
    )
    if invalid:
        raise ValueError("BTC absorption depth levels are not strictly ordered")
    return levels


def _depth_level(value: object) -> DepthLevel:
    if not isinstance(value, dict):
        raise ValueError("BTC absorption depth level must be a mapping")
    price, size = float(value.get("px", 0.0)), float(value.get("sz", 0.0))
    if (
        not math.isfinite(price)
        or not math.isfinite(size)
        or price <= 0.0
        or size <= 0.0
    ):
        raise ValueError("BTC absorption depth level values must be positive")
    return DepthLevel(price, size)


def _increment(counts: dict[str, int], reason: str) -> None:
    counts[reason] = counts.get(reason, 0) + 1
