"""Causal post-only order-book replay for backend Hypervelocity decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.research.maker_replay_validation import (
    validate_book,
    validate_trades,
)
from hypervector.strategies.hypervelocity_contract import HypervelocityContract

Direction = Literal["long", "short"]
FillRule = Literal["touch", "through", "trade-through"]


@dataclass(frozen=True)
class MakerReplayConfig:
    """Explicit maker-replay assumptions that remain reportable and tunable."""

    initial_equity: float = 10_000.0
    maker_fee_rate: float = 0.00015
    fill_rule: FillRule = "through"
    tick_size: float = 1.0
    entry_ttl_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.initial_equity <= 0.0:
            raise ValueError("initial_equity must be positive")
        if self.maker_fee_rate < 0.0:
            raise ValueError("maker_fee_rate must be non-negative")
        if self.fill_rule not in ("touch", "through", "trade-through"):
            raise ValueError("fill_rule must be touch|through|trade-through")
        if self.tick_size <= 0.0:
            raise ValueError("tick_size must be positive")
        if self.entry_ttl_seconds <= 0.0:
            raise ValueError("entry_ttl_seconds must be positive")


@dataclass(frozen=True)
class MakerReplayTrade:
    """One completed maker-to-maker trade reconstructed from market evidence."""

    direction: Direction
    signal_time_utc: str
    submitted_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    quantity: float
    margin: float
    notional: float
    gross_pnl: float
    fees: float
    net_pnl: float
    entry_wait_seconds: float
    hold_seconds: float


@dataclass(frozen=True)
class MakerReplayReport:
    """Complete maker replay including unresolved order uncertainty."""

    fill_rule: FillRule
    snapshots: int
    market_trade_prints: int
    submitted_entries: int
    entry_fills: int
    expired_entries: int
    canceled_entries: int
    pending_orders: int
    completed_trades: int
    open_positions: int
    initial_equity: float
    final_equity: float
    submission_times_utc: tuple[str, ...]
    trades: tuple[MakerReplayTrade, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe replay report."""
        return asdict(self)


@dataclass
class _PendingEntry:
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    limit_price: float
    trade_through_volume: float = 0.0


@dataclass
class _OpenPosition:
    direction: Direction
    signal_time: pd.Timestamp
    submitted_time: pd.Timestamp
    entry_time: pd.Timestamp
    entry_price: float
    quantity: float
    margin: float
    notional: float
    target_price: float
    exit_trade_through_volume: float = 0.0


@dataclass
class _ReplayState:
    equity: float
    pending: _PendingEntry | None = None
    position: _OpenPosition | None = None
    expired_direction: Direction | None = None
    last_signal: pd.Timestamp | None = None
    submitted: int = 0
    entry_fills: int = 0
    expired: int = 0
    canceled: int = 0
    submissions: list[str] = field(default_factory=list)
    trades: list[MakerReplayTrade] = field(default_factory=list)


def _direction_rows(decisions: pd.DataFrame) -> pd.Series:
    required = {"primary_regime", "breakout_direction"}
    missing = required.difference(decisions.columns)
    if missing:
        raise ValueError(f"maker replay decisions missing columns: {sorted(missing)}")
    primary = decisions["primary_regime"].astype(str)
    breakout = decisions["breakout_direction"].astype(object)
    result = pd.Series(None, index=decisions.index, dtype=object)
    result = result.mask(primary.eq(PrimaryRegime.TREND_UP.value), "long")
    result = result.mask(primary.eq(PrimaryRegime.TREND_DOWN.value), "short")
    result = result.mask(
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.UPWARD.value),
        "long",
    )
    return result.mask(
        primary.eq(PrimaryRegime.BREAKOUT.value)
        & breakout.eq(BreakoutDirection.DOWNWARD.value),
        "short",
    )


def _available_directions(decisions: pd.DataFrame) -> pd.Series:
    if not isinstance(decisions.index, pd.DatetimeIndex):
        raise ValueError("maker replay decisions require a DatetimeIndex")
    directions = _direction_rows(decisions)
    directions.index = directions.index + pd.Timedelta(minutes=1)
    return directions


def _desired_at(
    directions: pd.Series,
    timestamp: pd.Timestamp,
) -> tuple[Direction | None, pd.Timestamp | None]:
    position = int(directions.index.searchsorted(timestamp, side="right")) - 1
    if position < 0:
        return None, None
    value = directions.iloc[position]
    direction: Direction | None = value if value in ("long", "short") else None
    return direction, pd.Timestamp(directions.index[position])


def _fill_reached(
    *,
    side: Literal["buy", "sell"],
    limit_price: float,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    if config.fill_rule == "trade-through":
        return False
    clearance = config.tick_size if config.fill_rule == "through" else 0.0
    if side == "buy":
        return ask <= limit_price - clearance
    return bid >= limit_price + clearance


def _trade_reached(
    *,
    side: Literal["buy", "sell"],
    limit_price: float,
    aggressor_side: str,
    trade_price: float,
) -> bool:
    if side == "buy":
        return aggressor_side == "sell" and trade_price < limit_price
    return aggressor_side == "buy" and trade_price > limit_price


def _entry_filled(
    pending: _PendingEntry,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    side: Literal["buy", "sell"] = "buy" if pending.direction == "long" else "sell"
    return _fill_reached(
        side=side,
        limit_price=pending.limit_price,
        bid=bid,
        ask=ask,
        config=config,
    )


def _open_position(
    pending: _PendingEntry,
    timestamp: pd.Timestamp,
    equity: float,
    contract: HypervelocityContract,
) -> _OpenPosition:
    allocation = contract.allocate(equity)
    quantity = allocation.notional / pending.limit_price
    multiplier = (
        1.0 + contract.target_price_fraction
        if pending.direction == "long"
        else 1.0 - contract.target_price_fraction
    )
    return _OpenPosition(
        pending.direction,
        pending.signal_time,
        pending.submitted_time,
        timestamp,
        pending.limit_price,
        quantity,
        allocation.margin,
        allocation.notional,
        pending.limit_price * multiplier,
    )


def _exit_filled(
    position: _OpenPosition,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    side: Literal["buy", "sell"] = "sell" if position.direction == "long" else "buy"
    return _fill_reached(
        side=side,
        limit_price=position.target_price,
        bid=bid,
        ask=ask,
        config=config,
    )


def _close_trade(
    position: _OpenPosition,
    timestamp: pd.Timestamp,
    fee_rate: float,
) -> MakerReplayTrade:
    sign = 1.0 if position.direction == "long" else -1.0
    gross = position.quantity * (position.target_price - position.entry_price) * sign
    fees = position.quantity * (position.entry_price + position.target_price) * fee_rate
    return MakerReplayTrade(
        position.direction,
        position.signal_time.isoformat(),
        position.submitted_time.isoformat(),
        position.entry_time.isoformat(),
        timestamp.isoformat(),
        position.entry_price,
        position.target_price,
        position.quantity,
        position.margin,
        position.notional,
        gross,
        fees,
        gross - fees,
        (position.entry_time - position.submitted_time).total_seconds(),
        (timestamp - position.entry_time).total_seconds(),
    )


def _replay_snapshot(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    desired: Direction | None,
    signal_time: pd.Timestamp | None,
    config: MakerReplayConfig,
    contract: HypervelocityContract,
) -> None:
    if state.expired_direction is not None and desired != state.expired_direction:
        state.expired_direction = None
    pending = state.pending
    if pending is not None:
        age = (timestamp - pending.submitted_time).total_seconds()
        if desired != pending.direction:
            state.pending, state.canceled = None, state.canceled + 1
        elif age > config.entry_ttl_seconds:
            state.pending, state.expired = None, state.expired + 1
            state.expired_direction = pending.direction
        elif _entry_filled(pending, bid, ask, config):
            state.position = _open_position(pending, timestamp, state.equity, contract)
            state.pending, state.entry_fills = None, state.entry_fills + 1
            return
    if state.position is not None and _exit_filled(state.position, bid, ask, config):
        trade = _close_trade(state.position, timestamp, config.maker_fee_rate)
        state.trades.append(trade)
        state.equity += trade.net_pnl
        state.position = None
        return
    can_submit = (
        state.pending is None
        and state.position is None
        and desired is not None
        and desired != state.expired_direction
    )
    if can_submit and signal_time is not None and signal_time != state.last_signal:
        limit_price = bid if desired == "long" else ask
        state.pending = _PendingEntry(desired, signal_time, timestamp, limit_price)
        state.last_signal = signal_time
        state.submitted += 1
        state.submissions.append(timestamp.isoformat())


def _replay_pending_trade(
    state: _ReplayState,
    pending: _PendingEntry,
    timestamp: pd.Timestamp,
    aggressor_side: str,
    trade_price: float,
    trade_size: float,
    desired: Direction | None,
    config: MakerReplayConfig,
    contract: HypervelocityContract,
) -> bool:
    age = (timestamp - pending.submitted_time).total_seconds()
    side: Literal["buy", "sell"] = "buy" if pending.direction == "long" else "sell"
    qualifies = timestamp > pending.submitted_time and _trade_reached(
        side=side,
        limit_price=pending.limit_price,
        aggressor_side=aggressor_side,
        trade_price=trade_price,
    )
    if qualifies:
        pending.trade_through_volume += trade_size
    required = contract.allocate(state.equity).notional / pending.limit_price
    if desired != pending.direction:
        state.pending, state.canceled = None, state.canceled + 1
    elif age > config.entry_ttl_seconds:
        state.pending, state.expired = None, state.expired + 1
        state.expired_direction = pending.direction
    elif pending.trade_through_volume >= required:
        state.position = _open_position(pending, timestamp, state.equity, contract)
        state.pending, state.entry_fills = None, state.entry_fills + 1
        return True
    return False


def _replay_trade(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    aggressor_side: str,
    trade_price: float,
    trade_size: float,
    desired: Direction | None,
    config: MakerReplayConfig,
    contract: HypervelocityContract,
) -> None:
    if state.expired_direction is not None and desired != state.expired_direction:
        state.expired_direction = None
    pending = state.pending
    if pending is not None and _replay_pending_trade(
        state,
        pending,
        timestamp,
        aggressor_side,
        trade_price,
        trade_size,
        desired,
        config,
        contract,
    ):
        return
    position = state.position
    if position is None or timestamp <= position.entry_time:
        return
    exit_side: Literal["buy", "sell"] = (
        "sell" if position.direction == "long" else "buy"
    )
    if _trade_reached(
        side=exit_side,
        limit_price=position.target_price,
        aggressor_side=aggressor_side,
        trade_price=trade_price,
    ):
        position.exit_trade_through_volume += trade_size
    if position.exit_trade_through_volume >= position.quantity:
        trade = _close_trade(position, timestamp, config.maker_fee_rate)
        state.trades.append(trade)
        state.equity += trade.net_pnl
        state.position = None


def _event_tape(
    snapshots: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    books = snapshots.assign(event_kind="book", event_priority=0)
    prints = trades.assign(event_kind="trade", event_priority=1)
    return (
        pd.concat((books, prints), ignore_index=True)
        .sort_values(["ts_ms", "event_priority"])
        .reset_index(drop=True)
    )


def _execute_tape(
    tape: pd.DataFrame,
    directions: pd.Series,
    config: MakerReplayConfig,
) -> _ReplayState:
    state = _ReplayState(equity=config.initial_equity)
    contract = HypervelocityContract()
    for row in tape.itertuples(index=False):
        timestamp = pd.Timestamp(int(row.ts_ms), unit="ms", tz="UTC")
        desired, signal_time = _desired_at(directions, timestamp)
        if getattr(row, "event_kind", "book") == "trade":
            _replay_trade(
                state,
                timestamp,
                str(row.aggressor_side),
                float(row.price),
                float(row.size),
                desired,
                config,
                contract,
            )
        else:
            _replay_snapshot(
                state,
                timestamp,
                float(row.best_bid),
                float(row.best_ask),
                desired,
                signal_time,
                config,
                contract,
            )
    return state


def replay_maker_orders(
    book: pd.DataFrame,
    decisions: pd.DataFrame,
    config: MakerReplayConfig | None = None,
    *,
    trades: pd.DataFrame | None = None,
) -> MakerReplayReport:
    """Replay post-only entries and fixed targets from causal market evidence."""
    cfg = config or MakerReplayConfig()
    snapshots = validate_book(book)
    prints = validate_trades(trades) if cfg.fill_rule == "trade-through" else None
    tape = _event_tape(snapshots, prints) if prints is not None else snapshots
    directions = _available_directions(decisions)
    state = _execute_tape(tape, directions, cfg)
    return MakerReplayReport(
        cfg.fill_rule,
        len(snapshots),
        0 if prints is None else len(prints),
        state.submitted,
        state.entry_fills,
        state.expired,
        state.canceled,
        int(state.pending is not None),
        len(state.trades),
        int(state.position is not None),
        cfg.initial_equity,
        state.equity,
        tuple(state.submissions),
        tuple(state.trades),
        (
            (
                "trade-through requires cumulative volume beyond limits but cannot observe queue rank"
                if prints is not None
                else "book-only fill rules do not observe executed trade prints"
            ),
            "queue position, cancellations, and partial maker fills are unknown",
            "touch and book-through remain assumption challengers, not guarantees",
        ),
    )
