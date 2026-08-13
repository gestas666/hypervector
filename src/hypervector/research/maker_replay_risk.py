"""Risk accounting for the bounded Hypervelocity maker replay."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

import pandas as pd

from hypervector.nautilus.hyperliquid_margin import (
    IsolatedMarginPosition,
    maintenance_rate_for_max_leverage,
)
from hypervector.paper.liquidation_execution import (
    LIQUIDATION_COOLDOWN_MS,
    PARTIAL_LIQUIDATION_FRACTION,
    PARTIAL_LIQUIDATION_THRESHOLD_USD,
)
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    MakerReplayLifecycle,
    MakerReplayTrade,
    OpenPosition,
    ReplayState,
)


def marked_equity(state: ReplayState, mark_price: float) -> float:
    """Return realized equity plus current open-position PnL."""
    position = state.position
    if position is None:
        return state.equity
    sign = 1.0 if position.direction == "long" else -1.0
    unrealized = sign * position.quantity * (mark_price - position.entry_price)
    return state.equity + unrealized


def update_drawdown(state: ReplayState, mark_price: float) -> None:
    """Update close/event marked drawdown without inventing intratick ordering."""
    marked = marked_equity(state, mark_price)
    state.last_marked_equity = marked
    state.peak_equity = max(state.peak_equity, marked)
    if state.peak_equity <= 0.0:
        return
    drawdown = 100.0 * (marked - state.peak_equity) / state.peak_equity
    state.maximum_drawdown_pct = min(state.maximum_drawdown_pct, drawdown)


def _peak_stop_price(
    position: OpenPosition,
    peak_margin_pct: float,
    lock_ratio: float,
) -> float:
    leverage = position.notional / position.margin
    locked_price_fraction = peak_margin_pct * lock_ratio / 100.0 / leverage
    multiplier = (
        1.0 + locked_price_fraction
        if position.direction == "long"
        else 1.0 - locked_price_fraction
    )
    return position.entry_price * multiplier


def _peak_stop_tightens(
    position: OpenPosition,
    candidate: float,
    minimum_move: float,
) -> bool:
    current = position.stop_price
    if current is None:
        return True
    if position.direction == "long":
        return candidate - current > minimum_move
    return current - candidate > minimum_move


def update_peak_protection(
    state: ReplayState,
    timestamp: pd.Timestamp,
    mark_price: float,
    config: MakerReplayConfig,
) -> bool:
    """Tighten a source-derived peak stop from causal authentic mark evidence."""
    position = state.position
    activation = config.peak_protection_activation_margin_pct
    lock_ratio = config.peak_protection_lock_ratio
    if position is None or activation is None or lock_ratio is None:
        return False
    sign = 1.0 if position.direction == "long" else -1.0
    leverage = position.notional / position.margin
    margin_pct = sign * (mark_price / position.entry_price - 1.0) * leverage * 100.0
    if margin_pct > position.peak_margin_pnl_pct:
        position.peak_margin_pnl_pct = margin_pct
    peak_margin_pct = position.peak_margin_pnl_pct
    if peak_margin_pct < activation:
        return False
    timestamp_ms = int(timestamp.timestamp() * 1000)
    last_update = position.peak_protection_last_update_ms
    cooldown_ms = config.peak_protection_update_cooldown_seconds * 1000.0
    if last_update is not None and timestamp_ms - last_update < cooldown_ms:
        return False
    candidate = _peak_stop_price(position, peak_margin_pct, lock_ratio)
    minimum = position.entry_price * config.peak_protection_minimum_price_move_fraction
    if not _peak_stop_tightens(position, candidate, minimum):
        return False
    first_arm = not position.peak_protection_armed
    position.stop_price = candidate
    position.peak_protection_armed = True
    position.peak_protection_last_update_ms = timestamp_ms
    state.peak_protection_updates += 1
    if first_arm:
        state.peak_protection_arms += 1
    return True


def _margin_position(
    position: OpenPosition,
) -> IsolatedMarginPosition:
    leverage = position.notional / position.margin
    current_margin = position.quantity * position.entry_price / leverage
    return IsolatedMarginPosition(
        symbol="BTC",
        side=position.direction,
        quantity=position.quantity,
        entry_price=position.entry_price,
        isolated_margin=current_margin,
        maintenance_rate=maintenance_rate_for_max_leverage(position.venue_max_leverage),
        fees_paid_usd=_open_fee_basis(position),
        funding_net_usd=_open_funding_basis(position),
    )


def _open_fee_basis(position: OpenPosition) -> float:
    basis = position.open_fee_basis
    return position.entry_fee + position.liquidation_fees if basis is None else basis


def _open_funding_basis(position: OpenPosition) -> float:
    basis = position.open_funding_basis
    return position.funding_cashflow if basis is None else basis


def _scale_open_cost_basis(
    position: OpenPosition,
    before_quantity: float,
    fee_basis: float,
    funding_basis: float,
) -> None:
    retained_fraction = position.quantity / before_quantity
    position.open_fee_basis = fee_basis * retained_fraction
    position.open_funding_basis = funding_basis * retained_fraction


def position_liquidation_price(position: OpenPosition) -> float:
    """Return the modeled isolated liquidation boundary for an open position."""
    return _margin_position(position).liquidation_price()


def _liquidation_quantity(
    position: OpenPosition,
    mark_price: float,
    timestamp_ms: int,
) -> tuple[float, bool]:
    in_cooldown = (
        position.last_partial_liquidation_ms is not None
        and timestamp_ms - position.last_partial_liquidation_ms
        < LIQUIDATION_COOLDOWN_MS
    )
    partial = position.quantity * mark_price > PARTIAL_LIQUIDATION_THRESHOLD_USD
    if partial and not in_cooldown:
        return position.quantity * PARTIAL_LIQUIDATION_FRACTION, True
    return position.quantity, False


def _complete_lifecycle(
    state: ReplayState,
    position: OpenPosition,
    trade: MakerReplayTrade,
    status: str,
) -> None:
    current = state.lifecycles[position.lifecycle_id]
    state.lifecycles[position.lifecycle_id] = MakerReplayLifecycle(
        **{
            **asdict(current),
            "outcome_time_utc": trade.exit_time_utc,
            "status": status,
            "exit_price": trade.exit_price,
            "fees": trade.fees,
            "net_pnl": trade.net_pnl,
            "stop_price": position.stop_price,
        }
    )


def complete_target(
    state: ReplayState,
    timestamp: pd.Timestamp,
    fee_rate: float,
    mark_price: float,
) -> None:
    """Close the remaining position at its maker target and update equity."""
    position = state.position
    if position is None:
        raise RuntimeError("target completion requires an open position")
    sign = 1.0 if position.direction == "long" else -1.0
    current_gross = (
        sign * position.quantity * (position.target_price - position.entry_price)
    )
    gross = position.realized_gross_pnl + current_gross
    exit_fee = position.quantity * position.target_price * fee_rate
    fees = position.entry_fee + position.liquidation_fees + exit_fee
    quantity = position.initial_quantity or position.quantity
    net_pnl = gross - fees + position.funding_cashflow
    trade = MakerReplayTrade(
        position.direction,
        position.signal_time.isoformat(),
        position.submitted_time.isoformat(),
        position.entry_time.isoformat(),
        timestamp.isoformat(),
        position.entry_price,
        position.target_price,
        quantity,
        position.margin,
        position.notional,
        gross,
        fees,
        net_pnl,
        (position.entry_time - position.submitted_time).total_seconds(),
        (timestamp - position.entry_time).total_seconds(),
        "target_completed",
        position.funding_cashflow,
    )
    state.equity += current_gross - exit_fee
    _complete_lifecycle(state, position, trade, "target_completed")
    state.trades.append(trade)
    _record_target_completion(state, position, timestamp)
    state.position = None
    update_drawdown(state, mark_price)


def _record_target_completion(
    state: ReplayState,
    position: OpenPosition,
    timestamp: pd.Timestamp,
) -> None:
    state.completed_direction = position.direction
    state.completed_status = (
        "target_completed" if position.liquidation_fees == 0.0 else "liquidated"
    )
    if state.completed_status == "target_completed":
        state.target_completions_in_episode += 1
    state.completed_reference_price = position.target_price
    state.last_exit_time = timestamp


def _liquidation_trade(
    position: OpenPosition,
    timestamp: pd.Timestamp,
    exit_price: float,
    gross: float,
    fees: float,
) -> MakerReplayTrade:
    quantity = position.initial_quantity or position.quantity
    return MakerReplayTrade(
        position.direction,
        position.signal_time.isoformat(),
        position.submitted_time.isoformat(),
        position.entry_time.isoformat(),
        timestamp.isoformat(),
        position.entry_price,
        exit_price,
        quantity,
        position.margin,
        position.notional,
        gross,
        fees,
        gross - fees + position.funding_cashflow,
        (position.entry_time - position.submitted_time).total_seconds(),
        (timestamp - position.entry_time).total_seconds(),
        "liquidated",
        position.funding_cashflow,
    )


def _risk_exit_trade(
    position: OpenPosition,
    timestamp: pd.Timestamp,
    exit_price: float,
    gross: float,
    fees: float,
    status: Literal["stopped", "time_exited", "regime_exited", "reversed"],
) -> MakerReplayTrade:
    quantity = position.initial_quantity or position.quantity
    return MakerReplayTrade(
        position.direction,
        position.signal_time.isoformat(),
        position.submitted_time.isoformat(),
        position.entry_time.isoformat(),
        timestamp.isoformat(),
        position.entry_price,
        exit_price,
        quantity,
        position.margin,
        position.notional,
        gross,
        fees,
        gross - fees + position.funding_cashflow,
        (position.entry_time - position.submitted_time).total_seconds(),
        (timestamp - position.entry_time).total_seconds(),
        status,
        position.funding_cashflow,
    )


def apply_book_regime_exit(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    structural: Direction | None,
    config: MakerReplayConfig,
) -> bool:
    """Close at adverse BBO only after a causal opposite structural regime."""
    position = state.position
    if position is None or not config.opposite_regime_exit:
        return False
    if timestamp <= position.entry_time or structural is None:
        return False
    if structural == position.direction:
        return False
    exit_price = bid if position.direction == "long" else ask
    sign = 1.0 if position.direction == "long" else -1.0
    current_gross = sign * position.quantity * (exit_price - position.entry_price)
    gross = position.realized_gross_pnl + current_gross
    exit_fee = position.quantity * exit_price * config.taker_fee_rate
    fees = position.entry_fee + position.liquidation_fees + exit_fee
    state.equity += current_gross - exit_fee
    trade = _risk_exit_trade(
        position, timestamp, exit_price, gross, fees, "regime_exited"
    )
    _complete_lifecycle(state, position, trade, "regime_exited")
    state.trades.append(trade)
    state.completed_direction = position.direction
    state.completed_status = "regime_exited"
    state.completed_reference_price = exit_price
    state.last_exit_time = timestamp
    state.regime_exits += 1
    state.position = None
    update_drawdown(state, (bid + ask) / 2.0)
    return True


def apply_book_entry_close_reverse(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    desired: Direction | None,
    structural: Direction | None,
    signal_time: pd.Timestamp | None,
    config: MakerReplayConfig,
) -> bool:
    """Close at adverse BBO on a new executable opposite entry signal."""
    position = state.position
    if position is None or not config.opposite_entry_close_reverse:
        return False
    if signal_time is None or signal_time <= position.entry_time:
        return False
    if desired is None or desired != structural or desired == position.direction:
        return False
    exit_price = bid if position.direction == "long" else ask
    sign = 1.0 if position.direction == "long" else -1.0
    current_gross = sign * position.quantity * (exit_price - position.entry_price)
    gross = position.realized_gross_pnl + current_gross
    exit_fee = position.quantity * exit_price * config.taker_fee_rate
    fees = position.entry_fee + position.liquidation_fees + exit_fee
    state.equity += current_gross - exit_fee
    trade = _risk_exit_trade(position, timestamp, exit_price, gross, fees, "reversed")
    _complete_lifecycle(state, position, trade, "reversed")
    state.trades.append(trade)
    state.completed_direction = position.direction
    state.completed_status = "reversed"
    state.completed_reference_price = exit_price
    state.last_exit_time = timestamp
    state.close_reversals += 1
    state.position = None
    update_drawdown(state, (bid + ask) / 2.0)
    return True


def apply_book_stop(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    """Close remaining quantity at adverse BBO after a frozen stop trigger."""
    position = state.position
    if position is None or position.stop_price is None:
        return False
    if timestamp <= position.entry_time:
        return False
    triggered = (
        bid <= position.stop_price
        if position.direction == "long"
        else ask >= position.stop_price
    )
    if not triggered:
        return False
    exit_price = bid if position.direction == "long" else ask
    sign = 1.0 if position.direction == "long" else -1.0
    current_gross = sign * position.quantity * (exit_price - position.entry_price)
    gross = position.realized_gross_pnl + current_gross
    exit_fee = position.quantity * exit_price * config.taker_fee_rate
    fees = position.entry_fee + position.liquidation_fees + exit_fee
    state.equity += current_gross - exit_fee
    trade = _risk_exit_trade(position, timestamp, exit_price, gross, fees, "stopped")
    _complete_lifecycle(state, position, trade, "stopped")
    state.trades.append(trade)
    state.completed_direction = position.direction
    state.completed_status = "stopped"
    state.completed_reference_price = exit_price
    state.last_exit_time = timestamp
    state.stops += 1
    if position.peak_protection_armed:
        state.peak_protection_exits += 1
    state.position = None
    update_drawdown(state, (bid + ask) / 2.0)
    return True


def apply_book_time_exit(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    """Close a surviving position at adverse BBO after its holding deadline."""
    position = state.position
    maximum = (
        position.maximum_hold_seconds
        if position is not None and position.maximum_hold_seconds is not None
        else config.maximum_hold_seconds
    )
    if position is None or maximum is None:
        return False
    elapsed = (timestamp - position.entry_time).total_seconds()
    if elapsed < maximum:
        return False
    exit_price = bid if position.direction == "long" else ask
    sign = 1.0 if position.direction == "long" else -1.0
    current_gross = sign * position.quantity * (exit_price - position.entry_price)
    gross = position.realized_gross_pnl + current_gross
    exit_fee = position.quantity * exit_price * config.taker_fee_rate
    fees = position.entry_fee + position.liquidation_fees + exit_fee
    state.equity += current_gross - exit_fee
    trade = _risk_exit_trade(
        position, timestamp, exit_price, gross, fees, "time_exited"
    )
    _complete_lifecycle(state, position, trade, "time_exited")
    state.trades.append(trade)
    state.completed_direction = position.direction
    state.completed_status = "time_exited"
    state.completed_reference_price = exit_price
    state.last_exit_time = timestamp
    state.time_exits += 1
    state.position = None
    update_drawdown(state, (bid + ask) / 2.0)
    return True


def apply_book_liquidation(
    state: ReplayState,
    timestamp: pd.Timestamp,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
    trigger_mark: float | None = None,
) -> bool:
    """Apply BBO execution when the selected mark crosses maintenance."""
    position = state.position
    if position is None or timestamp <= position.entry_time:
        return False
    mark = trigger_mark if trigger_mark is not None else (bid + ask) / 2.0
    if not _margin_position(position).state(mark).liquidatable:
        return False
    timestamp_ms = int(timestamp.timestamp() * 1000)
    quantity, partial = _liquidation_quantity(position, mark, timestamp_ms)
    before_quantity = position.quantity
    fee_basis = _open_fee_basis(position)
    funding_basis = _open_funding_basis(position)
    exit_price = bid if position.direction == "long" else ask
    sign = 1.0 if position.direction == "long" else -1.0
    gross = sign * quantity * (exit_price - position.entry_price)
    fee = quantity * exit_price * config.taker_fee_rate
    state.equity += gross - fee
    position.realized_gross_pnl += gross
    position.liquidation_fees += fee
    position.quantity -= quantity
    if partial:
        _scale_open_cost_basis(
            position,
            before_quantity,
            fee_basis,
            funding_basis,
        )
        position.last_partial_liquidation_ms = timestamp_ms
        state.partial_liquidations += 1
        update_drawdown(state, mark)
        return True
    total_fees = position.entry_fee + position.liquidation_fees
    trade = _liquidation_trade(
        position,
        timestamp,
        exit_price,
        position.realized_gross_pnl,
        total_fees,
    )
    _complete_lifecycle(state, position, trade, "liquidated")
    state.trades.append(trade)
    state.completed_direction = position.direction
    state.completed_status = "liquidated"
    state.completed_reference_price = exit_price
    state.last_exit_time = timestamp
    state.liquidations += 1
    state.position = None
    update_drawdown(state, mark)
    return True
