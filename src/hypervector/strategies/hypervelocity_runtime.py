"""Pure order-lifecycle coordinator for the Hypervelocity backend."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from hypervector.execution import OrderCommand, VenueOrderEvent
from hypervector.paper.maker_execution import round_price_to_tick

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class RuntimeMarketState:
    """Pre-classified backend market input; no regime calculation occurs here."""

    symbol: str
    observed_at: str
    entry_direction: Direction | None
    entry_quantity: float
    entry_limit_price: float | None
    evidence_fresh: bool
    entry_ttl_seconds: float
    reentry_cooldown_seconds: float
    target_price_fraction: float
    price_tick: float

    def __post_init__(self) -> None:
        _nonempty(self.symbol, "symbol")
        _utc(self.observed_at, "observed_at")
        if self.entry_direction not in {None, "long", "short"}:
            raise ValueError("entry_direction must be long|short|None")
        _positive(self.entry_quantity, "entry_quantity")
        if self.entry_direction is not None:
            _positive(self.entry_limit_price, "entry_limit_price")
        elif self.entry_limit_price is not None:
            raise ValueError("flat market state cannot carry entry_limit_price")
        _nonnegative(self.entry_ttl_seconds, "entry_ttl_seconds")
        _nonnegative(self.reentry_cooldown_seconds, "reentry_cooldown_seconds")
        _positive(self.target_price_fraction, "target_price_fraction")
        _positive(self.price_tick, "price_tick")


@dataclass(frozen=True)
class RuntimeOrder:
    """Coordinator-owned state for one submitted venue command."""

    command: OrderCommand
    cumulative_quantity: float = 0.0
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        _nonnegative(self.cumulative_quantity, "cumulative_quantity")
        if self.cumulative_quantity > self.command.quantity:
            raise ValueError("cumulative quantity exceeds requested quantity")


@dataclass(frozen=True)
class HypervelocityRuntimeState:
    """Immutable state passed between pure coordinator advances."""

    next_order_sequence: int = 1
    pending_entry: RuntimeOrder | None = None
    active_targets: tuple[RuntimeOrder, ...] = ()
    terminal_order_ids: tuple[str, ...] = ()
    position_direction: Direction | None = None
    position_quantity: float = 0.0
    position_average_price: float | None = None
    expired_entry_direction: Direction | None = None
    completed_trade_direction: Direction | None = None
    last_exit_at: str | None = None

    def __post_init__(self) -> None:
        if self.next_order_sequence <= 0:
            raise ValueError("next_order_sequence must be positive")
        _nonnegative(self.position_quantity, "position_quantity")
        if self.position_quantity == 0.0:
            if self.position_direction is not None or self.position_average_price is not None:
                raise ValueError(
                    "flat position requires null position_direction and average price"
                )
        else:
            if self.position_direction not in {"long", "short"}:
                raise ValueError("open position requires position_direction")
            _positive(self.position_average_price, "position_average_price")
        if self.last_exit_at is not None:
            _utc(self.last_exit_at, "last_exit_at")


@dataclass(frozen=True)
class RuntimeDecision:
    """Pure coordinator output for execution and observability boundaries."""

    state: HypervelocityRuntimeState
    commands: tuple[OrderCommand, ...] = ()
    cancellations: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()


def advance_hypervelocity_runtime(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
    events: tuple[VenueOrderEvent, ...] = (),
) -> RuntimeDecision:
    """Apply venue evidence and derive deterministic backend order requests."""
    current = state
    commands: list[OrderCommand] = []
    annotations: list[str] = []
    for event in events:
        current, emitted, note = _apply_event(current, market, event)
        commands.extend(emitted)
        if note is not None:
            annotations.append(note)
    current = _rearm_consumed_direction(current, market.entry_direction)
    if not market.evidence_fresh:
        annotations.append("execution_evidence_uncertain")
        return RuntimeDecision(current, tuple(commands), annotations=tuple(annotations))
    current, cancellations = _manage_pending_entry(current, market)
    if _may_submit_entry(current, market):
        current, command = _new_entry(current, market)
        commands.append(command)
    return RuntimeDecision(
        current,
        tuple(commands),
        tuple(cancellations),
        tuple(annotations),
    )


def _apply_event(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
    event: VenueOrderEvent,
) -> tuple[HypervelocityRuntimeState, tuple[OrderCommand, ...], str | None]:
    if event.client_order_id in state.terminal_order_ids:
        return state, (), None
    if state.pending_entry is not None:
        if event.client_order_id == state.pending_entry.command.client_order_id:
            return _apply_entry_event(state, market, event)
    for target in state.active_targets:
        if event.client_order_id == target.command.client_order_id:
            return _apply_target_event(state, target, event)
    raise ValueError(f"venue event references unknown order {event.client_order_id!r}")


def _apply_entry_event(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
    event: VenueOrderEvent,
) -> tuple[HypervelocityRuntimeState, tuple[OrderCommand, ...], str | None]:
    pending = state.pending_entry
    if pending is None:
        raise ValueError("entry event requires pending entry")
    if event.event_type in {"partially_filled", "filled"}:
        if not _is_new_fill(pending, event):
            return state, (), None
        updated = replace(pending, cumulative_quantity=event.cumulative_quantity)
        state = _add_entry_fill(state, pending.command, event)
        state, target = _new_target(state, market, event)
        if event.event_type == "filled":
            state = _terminalize_entry(state, pending.command.client_order_id)
        else:
            state = replace(state, pending_entry=updated)
        return state, (target,), None
    if event.event_type in {"rejected", "expired"}:
        direction = _entry_direction(pending.command)
        state = _terminalize_entry(state, pending.command.client_order_id)
        return replace(state, expired_entry_direction=direction), (), event.event_type
    if event.event_type == "canceled":
        return _terminalize_entry(state, pending.command.client_order_id), (), None
    return state, (), None


def _apply_target_event(
    state: HypervelocityRuntimeState,
    target: RuntimeOrder,
    event: VenueOrderEvent,
) -> tuple[HypervelocityRuntimeState, tuple[OrderCommand, ...], str | None]:
    if event.event_type in {"partially_filled", "filled"}:
        if not _is_new_fill(target, event):
            return state, (), None
        remaining = state.position_quantity - event.last_quantity
        if remaining < -1e-12:
            raise ValueError("target fill exceeds open position quantity")
        if remaining <= 1e-12:
            return _close_position(state, event.event_at, event.client_order_id), (), None
        state = replace(state, position_quantity=remaining)
        targets = _replace_target(state.active_targets, target, event)
        state = replace(state, active_targets=targets)
        if event.event_type == "filled":
            state = replace(
                state,
                terminal_order_ids=state.terminal_order_ids + (
                    event.client_order_id,
                ),
            )
        return state, (), None
    if event.event_type in {"rejected", "expired", "canceled"}:
        state = replace(
            state,
            active_targets=tuple(item for item in state.active_targets if item != target),
            terminal_order_ids=state.terminal_order_ids + (event.client_order_id,),
        )
        return state, (), f"target_{event.event_type}"
    return state, (), None


def _add_entry_fill(
    state: HypervelocityRuntimeState,
    command: OrderCommand,
    event: VenueOrderEvent,
) -> HypervelocityRuntimeState:
    if event.fill_price is None:
        raise ValueError("entry fill requires price")
    direction = _entry_direction(command)
    if state.position_direction not in {None, direction}:
        raise ValueError("entry fill conflicts with open position direction")
    old_notional = state.position_quantity * (state.position_average_price or 0.0)
    quantity = state.position_quantity + event.last_quantity
    average = (old_notional + event.last_quantity * event.fill_price) / quantity
    return replace(
        state,
        position_direction=direction,
        position_quantity=quantity,
        position_average_price=average,
    )


def _new_target(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
    event: VenueOrderEvent,
) -> tuple[HypervelocityRuntimeState, OrderCommand]:
    if event.fill_price is None or state.position_direction is None:
        raise ValueError("target creation requires an entry fill")
    direction = state.position_direction
    multiplier = 1.0 + market.target_price_fraction
    if direction == "short":
        multiplier = 1.0 - market.target_price_fraction
    limit = round_price_to_tick(
        event.fill_price * multiplier,
        tick_size=market.price_tick,
        upward=direction == "long",
    )
    state, identity = _next_identity(state, market.symbol, "target")
    command = OrderCommand(
        client_order_id=identity,
        symbol=market.symbol,
        side="sell" if direction == "long" else "buy",
        quantity=event.last_quantity,
        order_type="limit",
        order_role="target",
        limit_price=limit,
        post_only=True,
        reduce_only=True,
        submitted_at=event.event_at,
    )
    return replace(state, active_targets=state.active_targets + (RuntimeOrder(command),)), command


def _manage_pending_entry(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
) -> tuple[HypervelocityRuntimeState, tuple[str, ...]]:
    pending = state.pending_entry
    if pending is None or pending.cancel_requested:
        return state, ()
    direction = _entry_direction(pending.command)
    changed = direction != market.entry_direction
    expired = _elapsed_seconds(pending.command.submitted_at, market.observed_at) > (
        market.entry_ttl_seconds
    )
    if not changed and not expired:
        return state, ()
    if expired:
        state = replace(state, expired_entry_direction=direction)
    pending = replace(pending, cancel_requested=True)
    return replace(state, pending_entry=pending), (pending.command.client_order_id,)


def _may_submit_entry(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
) -> bool:
    direction = market.entry_direction
    if direction is None or state.pending_entry is not None:
        return False
    if state.position_quantity > 0.0:
        return False
    if direction in {state.expired_entry_direction, state.completed_trade_direction}:
        return False
    if state.last_exit_at is None:
        return True
    return _elapsed_seconds(state.last_exit_at, market.observed_at) >= (
        market.reentry_cooldown_seconds
    )


def _new_entry(
    state: HypervelocityRuntimeState,
    market: RuntimeMarketState,
) -> tuple[HypervelocityRuntimeState, OrderCommand]:
    direction = market.entry_direction
    if direction is None or market.entry_limit_price is None:
        raise ValueError("entry submission requires directional market state")
    state, identity = _next_identity(state, market.symbol, "entry")
    command = OrderCommand(
        client_order_id=identity,
        symbol=market.symbol,
        side="buy" if direction == "long" else "sell",
        quantity=market.entry_quantity,
        order_type="limit",
        order_role="entry",
        limit_price=market.entry_limit_price,
        post_only=True,
        reduce_only=False,
        submitted_at=market.observed_at,
    )
    return replace(state, pending_entry=RuntimeOrder(command)), command


def _terminalize_entry(
    state: HypervelocityRuntimeState,
    order_id: str,
) -> HypervelocityRuntimeState:
    return replace(
        state,
        pending_entry=None,
        terminal_order_ids=state.terminal_order_ids + (order_id,),
    )


def _replace_target(
    targets: tuple[RuntimeOrder, ...],
    target: RuntimeOrder,
    event: VenueOrderEvent,
) -> tuple[RuntimeOrder, ...]:
    if event.event_type == "filled":
        return tuple(item for item in targets if item != target)
    updated = replace(target, cumulative_quantity=event.cumulative_quantity)
    return tuple(updated if item == target else item for item in targets)


def _is_new_fill(order: RuntimeOrder, event: VenueOrderEvent) -> bool:
    delta = event.cumulative_quantity - order.cumulative_quantity
    if delta < -1e-12:
        raise ValueError("cumulative fill quantity cannot regress")
    if abs(delta) <= 1e-12:
        return False
    if event.cumulative_quantity > order.command.quantity + 1e-12:
        raise ValueError("cumulative fill exceeds requested quantity")
    if abs(delta - event.last_quantity) > 1e-12:
        raise ValueError("last quantity must equal cumulative fill delta")
    return True


def _close_position(
    state: HypervelocityRuntimeState,
    event_at: str,
    filled_target_id: str,
) -> HypervelocityRuntimeState:
    completed = state.position_direction
    terminal = state.terminal_order_ids + tuple(
        target.command.client_order_id for target in state.active_targets
    )
    if filled_target_id not in terminal:
        terminal += (filled_target_id,)
    return replace(
        state,
        active_targets=(),
        terminal_order_ids=terminal,
        position_direction=None,
        position_quantity=0.0,
        position_average_price=None,
        completed_trade_direction=completed,
        last_exit_at=event_at,
    )


def _rearm_consumed_direction(
    state: HypervelocityRuntimeState,
    direction: Direction | None,
) -> HypervelocityRuntimeState:
    expired = state.expired_entry_direction
    completed = state.completed_trade_direction
    if expired is not None and direction != expired:
        expired = None
    if completed is not None and direction != completed:
        completed = None
    return replace(
        state,
        expired_entry_direction=expired,
        completed_trade_direction=completed,
    )


def _next_identity(
    state: HypervelocityRuntimeState,
    symbol: str,
    role: str,
) -> tuple[HypervelocityRuntimeState, str]:
    sequence = state.next_order_sequence
    identity = f"hv-{symbol.lower()}-{role}-{sequence:08d}"
    return replace(state, next_order_sequence=sequence + 1), identity


def _entry_direction(command: OrderCommand) -> Direction:
    return "long" if command.side == "buy" else "short"


def _elapsed_seconds(start: str, end: str) -> float:
    return (_utc(end, "end") - _utc(start, "start")).total_seconds()


def _utc(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must include an explicit UTC offset")
    return parsed


def _positive(value: float | None, name: str) -> None:
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _nonnegative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")


def _nonempty(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
