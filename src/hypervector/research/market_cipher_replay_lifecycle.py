"""Position lifecycle and accounting for Market Cipher replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    MarketCipherReplayTrade,
    ReplayExitLeg,
    ReplayExitReason,
)
from hypervector.research.market_cipher_replay_risk import (
    adverse_price,
    gap_adverse_price,
    position_liquidation_price,
)
from hypervector.research.market_cipher_replay_state import (
    ReplayOpenPosition,
    ReplayState,
)


def advance_open_positions(
    state: ReplayState,
    available: dict[str, pd.Series],
    timestamp: pd.Timestamp,
    config: MarketCipherReplayConfig,
) -> None:
    """Apply funding, barriers, trailing, and time exits for one timestamp."""
    for symbol in sorted(tuple(state.positions)):
        if symbol not in available:
            continue
        opened = state.positions[symbol]
        opened.bars_held += 1
        _settle_funding(state, opened, available[symbol], config)
        if _intrabar_exit(state, opened, available[symbol], timestamp, config):
            continue
        _schedule_or_timeout(state, opened, available[symbol], timestamp, config)


def close_position_leg(
    state: ReplayState,
    opened: ReplayOpenPosition,
    timestamp: pd.Timestamp,
    price: float,
    fraction_remaining: float,
    reason: ReplayExitReason,
    config: MarketCipherReplayConfig,
) -> None:
    """Realize one exact fraction of the currently remaining position."""
    quantity = opened.remaining_quantity * fraction_remaining
    sign = 1.0 if opened.candidate.direction == "long" else -1.0
    gross = sign * quantity * (price - opened.entry_price)
    fee_rate = _exit_fee_rate(reason, config)
    fee = quantity * price * fee_rate
    penalty = _liquidation_penalty(reason, quantity, price, config)
    opened.gross_pnl += gross
    opened.fees += fee
    opened.liquidation_penalty += penalty
    opened.legs.append(
        _exit_leg(opened, timestamp, reason, price, quantity, gross, fee, penalty)
    )
    state.equity += gross - fee - penalty
    _reduce_position(state, opened, quantity, timestamp, reason)


def update_marked_drawdown(state: ReplayState, available: dict[str, pd.Series]) -> None:
    """Mark open positions at the adverse bar extreme for drawdown."""
    marked = state.equity
    for symbol, opened in state.positions.items():
        if symbol not in available:
            continue
        column = "low" if opened.candidate.direction == "long" else "high"
        price = float(available[symbol][column])
        sign = 1.0 if opened.candidate.direction == "long" else -1.0
        marked += sign * opened.remaining_quantity * (price - opened.entry_price)
    update_replay_drawdown(state, marked)


def update_replay_drawdown(state: ReplayState, marked_equity: float) -> None:
    """Update the peak-to-trough percentage using supplied marked equity."""
    state.peak_equity = max(state.peak_equity, marked_equity)
    drawdown = 100.0 * (state.peak_equity - marked_equity) / state.peak_equity
    state.maximum_drawdown_pct = max(state.maximum_drawdown_pct, drawdown)


def force_end_closes(
    state: ReplayState,
    bars_by_symbol: dict[str, pd.DataFrame],
    config: MarketCipherReplayConfig,
) -> None:
    """Close every remaining position on its final available bar."""
    for symbol in sorted(tuple(state.positions)):
        opened = state.positions[symbol]
        bars = bars_by_symbol[symbol]
        timestamp = bars.index[-1]
        price = adverse_price(
            float(bars.iloc[-1]["close"]),
            opened.candidate.direction,
            config,
            entering=False,
        )
        close_position_leg(state, opened, timestamp, price, 1.0, "end_of_data", config)


def _settle_funding(
    state: ReplayState,
    opened: ReplayOpenPosition,
    bar: pd.Series,
    config: MarketCipherReplayConfig,
) -> None:
    rate = float(bar["funding_rate"]) * config.funding_rate_multiplier
    if rate == 0.0:
        return
    sign = 1.0 if opened.candidate.direction == "long" else -1.0
    cashflow = -sign * opened.remaining_quantity * float(bar["open"]) * rate
    opened.funding_total += cashflow
    opened.funding_open_basis += cashflow
    state.equity += cashflow


def _intrabar_exit(
    state: ReplayState,
    opened: ReplayOpenPosition,
    bar: pd.Series,
    timestamp: pd.Timestamp,
    config: MarketCipherReplayConfig,
) -> bool:
    liquidation = position_liquidation_price(opened, config)
    if _barrier_hit(opened, bar, liquidation, favorable=False):
        price = _market_barrier_price(opened, bar, liquidation, config)
        close_position_leg(state, opened, timestamp, price, 1.0, "liquidation", config)
        return True
    if _barrier_hit(opened, bar, opened.stop_price, favorable=False):
        price = _market_barrier_price(opened, bar, opened.stop_price, config)
        close_position_leg(state, opened, timestamp, price, 1.0, "stop", config)
        return True
    _process_targets(state, opened, bar, timestamp, config)
    return opened.candidate.symbol not in state.positions


def _market_barrier_price(
    opened: ReplayOpenPosition,
    bar: pd.Series,
    barrier: float,
    config: MarketCipherReplayConfig,
) -> float:
    raw = gap_adverse_price(opened.candidate.direction, barrier, float(bar["open"]))
    return adverse_price(raw, opened.candidate.direction, config, entering=False)


def _process_targets(
    state: ReplayState,
    opened: ReplayOpenPosition,
    bar: pd.Series,
    timestamp: pd.Timestamp,
    config: MarketCipherReplayConfig,
) -> None:
    risk_per_unit = abs(opened.entry_price - opened.stop_price)
    target_one = _target_price(opened, risk_per_unit)
    target_two = _target_price(opened, config.target_r_multiple * risk_per_unit)
    if _first_target_ready(opened, bar, target_one, config):
        close_position_leg(
            state, opened, timestamp, target_one, 0.25, "target_1r", config
        )
        opened.target_one_hit = True
    if _second_target_ready(opened, bar, target_two):
        fraction = 1.0 if config.exit_variant == "all_at_2r_control" else 0.5
        close_position_leg(
            state,
            opened,
            timestamp,
            target_two,
            fraction,
            "target_reward_risk",
            config,
        )
        opened.target_two_hit = True


def _first_target_ready(
    opened: ReplayOpenPosition,
    bar: pd.Series,
    target: float,
    config: MarketCipherReplayConfig,
) -> bool:
    return (
        config.exit_variant == "staged_25_50_trail"
        and not opened.target_one_hit
        and _barrier_hit(opened, bar, target, favorable=True)
    )


def _second_target_ready(
    opened: ReplayOpenPosition, bar: pd.Series, target: float
) -> bool:
    return not opened.target_two_hit and _barrier_hit(
        opened, bar, target, favorable=True
    )


def _target_price(opened: ReplayOpenPosition, distance: float) -> float:
    if opened.candidate.direction == "long":
        return opened.entry_price + distance
    return opened.entry_price - distance


def _barrier_hit(
    opened: ReplayOpenPosition,
    bar: pd.Series,
    price: float,
    *,
    favorable: bool,
) -> bool:
    long_high = (opened.candidate.direction == "long") == favorable
    observed = float(bar["high"] if long_high else bar["low"])
    return observed >= price if long_high else observed <= price


def _schedule_or_timeout(
    state: ReplayState,
    opened: ReplayOpenPosition,
    bar: pd.Series,
    timestamp: pd.Timestamp,
    config: MarketCipherReplayConfig,
) -> None:
    cross = int(bar["wave_cross"])
    opposite = -1 if opened.candidate.direction == "long" else 1
    if opened.target_two_hit and cross == opposite:
        opened.pending_exit = "opposite_wave_cross"
        return
    if opened.bars_held >= config.maximum_hold_bars:
        price = adverse_price(
            float(bar["close"]),
            opened.candidate.direction,
            config,
            entering=False,
        )
        close_position_leg(state, opened, timestamp, price, 1.0, "max_hold", config)


def _exit_fee_rate(reason: ReplayExitReason, config: MarketCipherReplayConfig) -> float:
    return (
        config.target_fee_rate
        if reason.startswith("target")
        else config.market_exit_fee_rate
    )


def _liquidation_penalty(
    reason: ReplayExitReason,
    quantity: float,
    price: float,
    config: MarketCipherReplayConfig,
) -> float:
    if reason != "liquidation":
        return 0.0
    return quantity * price * config.liquidation_penalty_rate


def _exit_leg(
    opened: ReplayOpenPosition,
    timestamp: pd.Timestamp,
    reason: ReplayExitReason,
    price: float,
    quantity: float,
    gross: float,
    fee: float,
    penalty: float,
) -> ReplayExitLeg:
    return ReplayExitLeg(
        timestamp.isoformat(),
        reason,
        price,
        quantity,
        quantity / opened.initial_quantity,
        gross,
        fee,
        penalty,
    )


def _reduce_position(
    state: ReplayState,
    opened: ReplayOpenPosition,
    quantity: float,
    timestamp: pd.Timestamp,
    reason: ReplayExitReason,
) -> None:
    prior = opened.remaining_quantity
    opened.remaining_quantity = max(0.0, prior - quantity)
    if opened.remaining_quantity > opened.initial_quantity * 1e-10:
        opened.funding_open_basis *= opened.remaining_quantity / prior
        return
    state.trades.append(_trade_record(opened, timestamp, reason, state.equity))
    del state.positions[opened.candidate.symbol]
    update_replay_drawdown(state, state.equity)


def _trade_record(
    opened: ReplayOpenPosition,
    timestamp: pd.Timestamp,
    reason: ReplayExitReason,
    equity_after: float,
) -> MarketCipherReplayTrade:
    net = opened.gross_pnl - opened.fees + opened.funding_total
    net -= opened.liquidation_penalty
    return MarketCipherReplayTrade(
        candidate=opened.candidate.candidate,
        signal_score=opened.candidate.score,
        symbol=opened.candidate.symbol,
        direction=opened.candidate.direction,
        signal_time_utc=opened.candidate.signal_time.isoformat(),
        entry_time_utc=opened.entry_time.isoformat(),
        exit_time_utc=timestamp.isoformat(),
        entry_price=opened.entry_price,
        exit_price=opened.legs[-1].price,
        stop_price=opened.stop_price,
        stop_distance_bps=opened.stop_distance_bps,
        liquidation_price=opened.initial_liquidation_price,
        risk_budget_usd=opened.risk_budget,
        initial_quantity=opened.initial_quantity,
        isolated_margin_usd=opened.initial_margin,
        gross_pnl_usd=opened.gross_pnl,
        fees_usd=opened.fees,
        funding_cashflow_usd=opened.funding_total,
        liquidation_penalty_usd=opened.liquidation_penalty,
        net_pnl_usd=net,
        equity_before_usd=opened.equity_before,
        equity_after_usd=equity_after,
        exit_reason=reason,
        exit_legs=tuple(opened.legs),
    )
