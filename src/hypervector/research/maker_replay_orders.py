"""Passive entry, fill, target, and stop order rules for maker replay."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from hypervector.research.maker_replay_contract import (
    MakerReplayPositionContract,
    target_price_for_entry,
)
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    OpenPosition,
    PendingEntry,
)
from hypervector.research.maker_replay_risk import position_liquidation_price


def fill_reached(
    *,
    side: Literal["buy", "sell"],
    limit_price: float,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    """Return whether touch/through BBO evidence fills a passive order."""
    if config.fill_rule == "trade-through":
        return False
    clearance = config.tick_size if config.fill_rule == "through" else 0.0
    if side == "buy":
        return ask <= limit_price - clearance
    return bid >= limit_price + clearance


def trade_reached(
    *,
    side: Literal["buy", "sell"],
    limit_price: float,
    aggressor_side: str,
    trade_price: float,
) -> bool:
    """Return whether a later aggressor print traded beyond a passive limit."""
    if side == "buy":
        return aggressor_side == "sell" and trade_price < limit_price
    return aggressor_side == "buy" and trade_price > limit_price


def entry_filled(
    pending: PendingEntry,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    """Return whether BBO evidence fills the pending entry."""
    side: Literal["buy", "sell"] = "buy" if pending.direction == "long" else "sell"
    return fill_reached(
        side=side,
        limit_price=pending.limit_price,
        bid=bid,
        ask=ask,
        config=config,
    )


def entry_limit_price(
    direction: Direction,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> float:
    """Return a tick-aligned passive limit behind the current touch."""
    depth = config.entry_depth_ticks * config.tick_size
    limit_price = bid - depth if direction == "long" else ask + depth
    if limit_price <= 0.0:
        raise ValueError("entry depth produces a non-positive limit price")
    return limit_price


def _entry_stop_price(
    position: OpenPosition,
    pending: PendingEntry,
    contract: MakerReplayPositionContract,
    config: MakerReplayConfig,
) -> float | None:
    decision_stop = pending.stop_price
    decision_margin_stop = pending.stop_margin_pct
    static_stop = (
        config.fixed_margin_stop_pct is not None
        or config.liquidation_proximity_stop_fraction is not None
    )
    decision_models = sum(
        value is not None for value in (decision_stop, decision_margin_stop)
    )
    if decision_models > 1:
        raise ValueError("only one decision stop model may be configured")
    if decision_models and static_stop:
        raise ValueError("decision stop cannot coexist with a static stop model")
    if decision_stop is not None:
        liquidation = position_liquidation_price(position)
        if position.direction == "long":
            return (
                decision_stop
                if liquidation < decision_stop < position.entry_price
                else None
            )
        return (
            decision_stop
            if position.entry_price < decision_stop < liquidation
            else None
        )
    margin_stop = (
        decision_margin_stop
        if decision_margin_stop is not None
        else config.fixed_margin_stop_pct
    )
    if margin_stop is not None:
        price_fraction = margin_stop / 100.0 / contract.leverage
        multiplier = (
            1.0 - price_fraction
            if position.direction == "long"
            else 1.0 + price_fraction
        )
        return position.entry_price * multiplier
    fraction = config.liquidation_proximity_stop_fraction
    if fraction is None:
        return None
    liquidation = position_liquidation_price(position)
    return position.entry_price + fraction * (liquidation - position.entry_price)


def open_position(
    pending: PendingEntry,
    timestamp: pd.Timestamp,
    equity: float,
    contract: MakerReplayPositionContract,
    config: MakerReplayConfig,
) -> OpenPosition:
    """Create one fixed-contract position and freeze its optional stop."""
    allocation = contract.allocate(equity * pending.allocation_multiplier)
    quantity = allocation.notional / pending.limit_price
    entry_fee = quantity * pending.limit_price * config.maker_fee_rate
    position = OpenPosition(
        pending.lifecycle_id,
        pending.direction,
        pending.signal_time,
        pending.submitted_time,
        timestamp,
        pending.limit_price,
        quantity,
        allocation.margin,
        allocation.notional,
        target_price_for_entry(
            contract,
            entry_price=pending.limit_price,
            direction=pending.direction,
            target_price_points=config.target_price_points,
        ),
        initial_quantity=quantity,
        entry_fee=entry_fee,
        open_fee_basis=entry_fee,
        open_funding_basis=0.0,
        maximum_hold_seconds=pending.maximum_hold_seconds,
    )
    position.stop_price = _entry_stop_price(position, pending, contract, config)
    return position


def exit_filled(
    position: OpenPosition,
    bid: float,
    ask: float,
    config: MakerReplayConfig,
) -> bool:
    """Return whether BBO evidence fills the passive fixed target."""
    side: Literal["buy", "sell"] = "sell" if position.direction == "long" else "buy"
    return fill_reached(
        side=side,
        limit_price=position.target_price,
        bid=bid,
        ask=ask,
        config=config,
    )
