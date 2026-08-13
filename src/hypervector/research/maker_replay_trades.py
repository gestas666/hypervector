"""Public-trade-through handling for causal maker replay."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from hypervector.research.maker_replay_contract import MakerReplayPositionContract
from hypervector.research.maker_replay_lifecycle import (
    mark_open,
    resolve_pending,
)
from hypervector.research.maker_replay_models import (
    Direction,
    MakerReplayConfig,
    PendingEntry,
    ReplayState,
)
from hypervector.research.maker_replay_orders import open_position, trade_reached
from hypervector.research.maker_replay_risk import complete_target, update_drawdown


def _replay_pending_trade(
    state: ReplayState,
    pending: PendingEntry,
    timestamp: pd.Timestamp,
    aggressor_side: str,
    trade_price: float,
    trade_size: float,
    structural: Direction | None,
    config: MakerReplayConfig,
    contract: MakerReplayPositionContract,
) -> bool:
    age = (timestamp - pending.submitted_time).total_seconds()
    side: Literal["buy", "sell"] = "buy" if pending.direction == "long" else "sell"
    qualifies = timestamp > pending.submitted_time and trade_reached(
        side=side,
        limit_price=pending.limit_price,
        aggressor_side=aggressor_side,
        trade_price=trade_price,
    )
    if qualifies:
        pending.trade_through_volume += trade_size
    required = (
        contract.allocate(state.equity * pending.allocation_multiplier).notional
        / pending.limit_price
    )
    if structural != pending.direction:
        resolve_pending(state, pending, timestamp, "canceled")
        state.pending, state.canceled = None, state.canceled + 1
    elif age > config.entry_ttl_seconds:
        resolve_pending(state, pending, timestamp, "expired")
        state.pending, state.expired = None, state.expired + 1
        state.expired_direction = pending.direction
    elif pending.trade_through_volume >= required:
        state.position = open_position(
            pending, timestamp, state.equity, contract, config
        )
        state.equity -= state.position.entry_fee
        mark_open(state, state.position)
        state.pending, state.entry_fills = None, state.entry_fills + 1
        return True
    return False


def replay_trade(
    state: ReplayState,
    timestamp: pd.Timestamp,
    aggressor_side: str,
    trade_price: float,
    trade_size: float,
    structural: Direction | None,
    config: MakerReplayConfig,
    contract: MakerReplayPositionContract,
) -> None:
    """Apply one public trade to pending entry or passive target evidence."""
    pending = state.pending
    if pending is not None and _replay_pending_trade(
        state,
        pending,
        timestamp,
        aggressor_side,
        trade_price,
        trade_size,
        structural,
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
    if trade_reached(
        side=exit_side,
        limit_price=position.target_price,
        aggressor_side=aggressor_side,
        trade_price=trade_price,
    ):
        position.exit_trade_through_volume += trade_size
    if position.exit_trade_through_volume >= position.quantity:
        complete_target(state, timestamp, config.maker_fee_rate, trade_price)
    if not state.authentic_context_enabled:
        update_drawdown(state, trade_price)
