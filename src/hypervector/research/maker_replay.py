"""Causal post-only order-book replay for backend Hypervelocity decisions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

import pandas as pd

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayReport,
    MakerReplayTrade,
    OpenPosition as _OpenPosition,
    PendingEntry as _PendingEntry,
    ReplayState as _ReplayState,
)
from hypervector.strategies.hypervelocity_contract import HypervelocityContract


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
        pending.lifecycle_id,
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


def _replace_lifecycle(
    state: _ReplayState,
    lifecycle_id: int,
    **changes: object,
) -> None:
    current = state.lifecycles[lifecycle_id]
    state.lifecycles[lifecycle_id] = MakerReplayLifecycle(
        **{**asdict(current), **changes}
    )


def _resolve_pending(
    state: _ReplayState,
    pending: _PendingEntry,
    timestamp: pd.Timestamp,
    status: Literal["expired", "canceled"],
) -> None:
    _replace_lifecycle(
        state,
        pending.lifecycle_id,
        outcome_time_utc=timestamp.isoformat(),
        status=status,
    )


def _mark_open(
    state: _ReplayState,
    position: _OpenPosition,
) -> None:
    _replace_lifecycle(
        state,
        position.lifecycle_id,
        entry_time_utc=position.entry_time.isoformat(),
        status="open",
        entry_price=position.entry_price,
        quantity=position.quantity,
    )


def _mark_closed(
    state: _ReplayState, position: _OpenPosition, trade: MakerReplayTrade
) -> None:
    _replace_lifecycle(
        state,
        position.lifecycle_id,
        outcome_time_utc=trade.exit_time_utc,
        status="target_completed",
        exit_price=trade.exit_price,
        fees=trade.fees,
        net_pnl=trade.net_pnl,
    )


def _submit_entry(
    state: _ReplayState,
    direction: Direction,
    signal_time: pd.Timestamp,
    timestamp: pd.Timestamp,
    limit_price: float,
) -> None:
    lifecycle_id = len(state.lifecycles)
    state.lifecycles.append(
        MakerReplayLifecycle(
            lifecycle_id,
            direction,
            signal_time.isoformat(),
            timestamp.isoformat(),
            None,
            None,
            "pending",
            None,
            None,
            None,
            None,
            None,
        )
    )
    state.pending = _PendingEntry(
        lifecycle_id, direction, signal_time, timestamp, limit_price
    )
    state.last_signal = signal_time
    state.submitted += 1
    state.submissions.append(timestamp.isoformat())


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
            _resolve_pending(state, pending, timestamp, "canceled")
            state.pending, state.canceled = None, state.canceled + 1
        elif age > config.entry_ttl_seconds:
            _resolve_pending(state, pending, timestamp, "expired")
            state.pending, state.expired = None, state.expired + 1
            state.expired_direction = pending.direction
        elif _entry_filled(pending, bid, ask, config):
            state.position = _open_position(pending, timestamp, state.equity, contract)
            _mark_open(state, state.position)
            state.pending, state.entry_fills = None, state.entry_fills + 1
            return
    if state.position is not None and _exit_filled(state.position, bid, ask, config):
        position = state.position
        trade = _close_trade(position, timestamp, config.maker_fee_rate)
        _mark_closed(state, position, trade)
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
        _submit_entry(state, desired, signal_time, timestamp, limit_price)


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
        _resolve_pending(state, pending, timestamp, "canceled")
        state.pending, state.canceled = None, state.canceled + 1
    elif age > config.entry_ttl_seconds:
        _resolve_pending(state, pending, timestamp, "expired")
        state.pending, state.expired = None, state.expired + 1
        state.expired_direction = pending.direction
    elif pending.trade_through_volume >= required:
        state.position = _open_position(pending, timestamp, state.equity, contract)
        _mark_open(state, state.position)
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
        _mark_closed(state, position, trade)
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
    state: _ReplayState | None = None,
) -> _ReplayState:
    active = state or _ReplayState(equity=config.initial_equity)
    contract = HypervelocityContract()
    timestamps = pd.to_datetime(tape["ts_ms"], unit="ms", utc=True)
    positions = directions.index.searchsorted(timestamps, side="right") - 1
    values = directions.to_numpy(dtype=object)
    for row, timestamp, position in zip(
        tape.itertuples(index=False), timestamps, positions, strict=True
    ):
        desired: Direction | None = None
        signal_time: pd.Timestamp | None = None
        if position >= 0:
            value = values[position]
            desired = value if value in ("long", "short") else None
            signal_time = pd.Timestamp(directions.index[position])
        if getattr(row, "event_kind", "book") == "trade":
            _replay_trade(
                active,
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
                active,
                timestamp,
                float(row.best_bid),
                float(row.best_ask),
                desired,
                signal_time,
                config,
                contract,
            )
    return active


def replay_maker_orders(
    book: pd.DataFrame,
    decisions: pd.DataFrame,
    config: MakerReplayConfig | None = None,
    *,
    trades: pd.DataFrame | None = None,
) -> MakerReplayReport:
    """Replay post-only entries and fixed targets from causal market evidence."""
    from hypervector.research.maker_replay_stream import (
        MakerReplayEvidenceChunk,
        replay_maker_order_chunks,
    )

    return replay_maker_order_chunks(
        (MakerReplayEvidenceChunk(book, trades),),
        decisions,
        config,
    )
