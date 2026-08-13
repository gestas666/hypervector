"""Atomic two-leg one-minute-path replay for residual research."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Literal

import pandas as pd

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    ResidualExitReason,
    ResidualPairReport,
    ResidualSignal,
    ResidualTrade,
)
from hypervector.research.cross_asset_residual_report import (
    build_residual_pair_report,
)
from hypervector.research.cross_asset_residual_replay_validation import (
    validated_minute_bars,
    validated_signals,
    validated_states,
)
from hypervector.research.low_tf_multi_asset_replay_risk import (
    adverse_low_tf_price,
    low_tf_liquidation_price,
)

_VENUE_MAX_LEVERAGE = {"BTC": 40.0, "ETH": 25.0, "SOL": 20.0, "HYPE": 10.0}
_LegDirection = Literal["long", "short"]
_PriceAnchor = Literal["open", "close"]


@dataclass
class _Leg:
    """Mutable accounting state for one isolated pair leg."""

    symbol: str
    direction: _LegDirection
    entry_price: float
    quantity: float
    isolated_margin: float
    entry_fee: float
    initial_liquidation_price: float = 0.0
    funding_cashflow: float = 0.0


@dataclass
class _OpenPair:
    """One open pair created from an atomic residual signal."""

    signal: ResidualSignal
    entry_time: pd.Timestamp
    left: _Leg
    right: _Leg
    equity_before: float


@dataclass
class _ReplayState:
    """Mutable shared-equity state for one pair cell."""

    equity: float
    peak_equity: float
    maximum_drawdown_pct: float = 0.0
    position: _OpenPair | None = None
    next_entry_eligible_at: pd.Timestamp | None = None
    conflict_rejections: int = 0
    trades: list[ResidualTrade] = field(default_factory=list)


def evaluate_residual_pair(
    *,
    minute_bars: dict[str, pd.DataFrame],
    states: pd.DataFrame,
    signals: tuple[ResidualSignal, ...],
    config: CrossAssetResidualConfig | None = None,
) -> ResidualPairReport:
    """Replay one declared pair with next-minute atomic two-leg execution."""
    cfg = config or CrossAssetResidualConfig()
    pair, bars = validated_minute_bars(minute_bars)
    minute_index = bars[pair[0]].index
    state_z = validated_states(states, minute_index)
    scheduled = validated_signals(signals, pair, minute_index)
    state = _ReplayState(cfg.initial_equity, cfg.initial_equity)
    for timestamp in minute_index:
        _close_from_residual_state(state, timestamp, state_z.get(timestamp), bars, cfg)
        _close_from_maximum_hold(state, timestamp, bars, cfg)
        _fill_signals(state, timestamp, scheduled.get(timestamp, ()), bars, cfg)
        _settle_funding(state, timestamp, bars)
        _liquidate_if_required(state, timestamp, bars, cfg)
        _update_marked_drawdown(state, timestamp, bars, cfg)
    _force_end_close(state, bars, cfg)
    return build_residual_pair_report(
        pair=pair,
        signal_count=len(signals),
        equity=state.equity,
        maximum_drawdown_pct=state.maximum_drawdown_pct,
        conflict_rejections=state.conflict_rejections,
        trades=tuple(state.trades),
        config=cfg,
    )


def _fill_signals(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    signals: tuple[ResidualSignal, ...],
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    for signal in signals:
        cooling = (
            state.next_entry_eligible_at is not None
            and timestamp < state.next_entry_eligible_at
        )
        if state.position is not None or cooling:
            state.conflict_rejections += 1
            continue
        opened = _open_pair(state, timestamp, signal, bars, config)
        state.position = opened


def _open_pair(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    signal: ResidualSignal,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> _OpenPair:
    left_direction, right_direction = _leg_directions(signal)
    gross_notional = state.equity * config.gross_notional_fraction
    right_weight = abs(signal.hedge_ratio)
    left_notional = gross_notional / (1.0 + right_weight)
    right_notional = gross_notional - left_notional
    left = _open_leg(
        signal.left_symbol,
        left_direction,
        left_notional,
        float(bars[signal.left_symbol].loc[timestamp, "open"]),
        config,
    )
    right = _open_leg(
        signal.right_symbol,
        right_direction,
        right_notional,
        float(bars[signal.right_symbol].loc[timestamp, "open"]),
        config,
    )
    before = state.equity
    state.equity -= left.entry_fee + right.entry_fee
    _update_drawdown(state, state.equity)
    return _OpenPair(signal, timestamp, left, right, before)


def _leg_directions(signal: ResidualSignal) -> tuple[_LegDirection, _LegDirection]:
    left_sign = 1 if signal.direction == "long_spread" else -1
    right_sign = -left_sign if signal.hedge_ratio > 0.0 else left_sign
    return (
        "long" if left_sign > 0 else "short",
        "long" if right_sign > 0 else "short",
    )


def _open_leg(
    symbol: str,
    direction: _LegDirection,
    notional: float,
    raw_price: float,
    config: CrossAssetResidualConfig,
) -> _Leg:
    price = adverse_low_tf_price(
        raw_price, direction, config.slippage_bps_per_side, entering=True
    )
    quantity = notional / price
    margin = notional / config.leverage
    fee = notional * config.fee_rate_per_side
    leg = _Leg(symbol, direction, price, quantity, margin, fee)
    leg.initial_liquidation_price = _leg_liquidation_price(leg)
    return leg


def _close_from_residual_state(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    zscore: float | None,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    opened = state.position
    if opened is None or zscore is None:
        return
    direction = opened.signal.direction
    adverse_stop = (
        zscore <= -config.stop_z
        if direction == "long_spread"
        else zscore >= config.stop_z
    )
    reason: ResidualExitReason | None = None
    if adverse_stop:
        reason = "residual_stop"
    elif abs(zscore) <= config.exit_z:
        reason = "mean_reversion"
    if reason is not None:
        _close_pair(state, timestamp, bars, zscore, reason, (), config)


def _close_from_maximum_hold(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    deadline = opened.entry_time + pd.Timedelta(minutes=5 * config.maximum_hold_bars)
    if timestamp >= deadline:
        _close_pair(state, timestamp, bars, math.nan, "maximum_hold", (), config)


def _settle_funding(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
) -> None:
    opened = state.position
    if opened is None:
        return
    for leg in (opened.left, opened.right):
        row = bars[leg.symbol].loc[timestamp]
        rate = float(row["funding_rate"])
        if rate == 0.0:
            continue
        sign = 1.0 if leg.direction == "long" else -1.0
        cashflow = -sign * leg.quantity * float(row["open"]) * rate
        leg.funding_cashflow += cashflow
        state.equity += cashflow
    _update_drawdown(state, state.equity)


def _liquidate_if_required(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    triggered = tuple(
        leg.symbol
        for leg in (opened.left, opened.right)
        if _leg_liquidated(leg, bars[leg.symbol].loc[timestamp])
    )
    if triggered:
        _close_pair(
            state,
            timestamp,
            bars,
            math.nan,
            "liquidation",
            triggered,
            config,
            price_anchor="close",
        )


def _leg_liquidated(leg: _Leg, row: pd.Series) -> bool:
    boundary = _leg_liquidation_price(leg)
    return (
        float(row["low"]) <= boundary
        if leg.direction == "long"
        else float(row["high"]) >= boundary
    )


def _leg_liquidation_price(leg: _Leg) -> float:
    return low_tf_liquidation_price(
        symbol=leg.symbol,
        direction=leg.direction,
        quantity=leg.quantity,
        entry_price=leg.entry_price,
        isolated_margin=leg.isolated_margin,
        entry_fee=leg.entry_fee,
        funding_cashflow=leg.funding_cashflow,
        venue_max_leverage=_VENUE_MAX_LEVERAGE[leg.symbol],
    )


def _close_pair(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    exit_zscore: float,
    reason: ResidualExitReason,
    liquidated_symbols: tuple[str, ...],
    config: CrossAssetResidualConfig,
    *,
    price_anchor: _PriceAnchor = "open",
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("cannot close a missing residual pair")
    exits = {
        leg.symbol: _exit_price(
            leg,
            bars[leg.symbol].loc[timestamp],
            leg.symbol in liquidated_symbols,
            config,
            price_anchor,
        )
        for leg in (opened.left, opened.right)
    }
    execution_time = timestamp + (
        pd.Timedelta(minutes=1) if price_anchor == "close" else pd.Timedelta(0)
    )
    _apply_close(
        state,
        execution_time,
        exits,
        exit_zscore,
        reason,
        liquidated_symbols,
        config,
    )


def _exit_price(
    leg: _Leg,
    row: pd.Series,
    liquidated: bool,
    config: CrossAssetResidualConfig,
    price_anchor: _PriceAnchor,
) -> float:
    raw = float(row[price_anchor])
    if liquidated:
        boundary = _leg_liquidation_price(leg)
        raw = min(raw, boundary) if leg.direction == "long" else max(raw, boundary)
    return adverse_low_tf_price(
        raw, leg.direction, config.slippage_bps_per_side, entering=False
    )


def _apply_close(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    exits: dict[str, float],
    exit_zscore: float,
    reason: ResidualExitReason,
    liquidated_symbols: tuple[str, ...],
    config: CrossAssetResidualConfig,
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("cannot apply close without an open pair")
    gross = sum(
        _leg_gross(leg, exits[leg.symbol]) for leg in (opened.left, opened.right)
    )
    exit_fees = sum(
        leg.quantity * exits[leg.symbol] * config.fee_rate_per_side
        for leg in (opened.left, opened.right)
    )
    penalty = sum(
        leg.quantity * exits[leg.symbol] * config.liquidation_penalty_rate
        for leg in (opened.left, opened.right)
        if leg.symbol in liquidated_symbols
    )
    state.equity += gross - exit_fees - penalty
    state.trades.append(
        _trade(
            opened,
            timestamp,
            exits,
            exit_zscore,
            gross,
            exit_fees,
            penalty,
            reason,
            state.equity,
        )
    )
    state.position = None
    state.next_entry_eligible_at = timestamp + pd.Timedelta(
        minutes=5 * config.reentry_cooldown_bars
    )
    _update_drawdown(state, state.equity)


def _leg_gross(leg: _Leg, exit_price: float) -> float:
    sign = 1.0 if leg.direction == "long" else -1.0
    return sign * leg.quantity * (exit_price - leg.entry_price)


def _trade(
    opened: _OpenPair,
    timestamp: pd.Timestamp,
    exits: dict[str, float],
    exit_zscore: float,
    gross: float,
    exit_fees: float,
    penalty: float,
    reason: ResidualExitReason,
    equity_after: float,
) -> ResidualTrade:
    entry_fees = opened.left.entry_fee + opened.right.entry_fee
    funding = opened.left.funding_cashflow + opened.right.funding_cashflow
    net = gross - entry_fees - exit_fees + funding - penalty
    return ResidualTrade(
        opened.left.symbol,
        opened.right.symbol,
        opened.signal.direction,
        opened.signal.decision_time_utc,
        opened.entry_time.isoformat(),
        timestamp.isoformat(),
        opened.left.direction,
        opened.right.direction,
        opened.signal.hedge_ratio,
        opened.signal.zscore,
        exit_zscore,
        opened.left.entry_price,
        opened.right.entry_price,
        exits[opened.left.symbol],
        exits[opened.right.symbol],
        opened.left.quantity,
        opened.right.quantity,
        opened.left.isolated_margin + opened.right.isolated_margin,
        opened.left.initial_liquidation_price,
        opened.right.initial_liquidation_price,
        gross,
        entry_fees + exit_fees,
        funding,
        penalty,
        net,
        opened.equity_before,
        equity_after,
        reason,
    )


def _update_marked_drawdown(
    state: _ReplayState,
    timestamp: pd.Timestamp,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    marked = state.equity
    if state.position is not None:
        legs = (state.position.left, state.position.right)
        exits = {
            leg.symbol: _exit_price(
                leg,
                bars[leg.symbol].loc[timestamp],
                False,
                config,
                "close",
            )
            for leg in legs
        }
        marked += sum(_leg_gross(leg, exits[leg.symbol]) for leg in legs)
        marked -= sum(
            leg.quantity * exits[leg.symbol] * config.fee_rate_per_side for leg in legs
        )
    _update_drawdown(state, marked)


def _update_drawdown(state: _ReplayState, equity: float) -> None:
    state.peak_equity = max(state.peak_equity, equity)
    drawdown = (state.peak_equity - equity) / state.peak_equity * 100.0
    state.maximum_drawdown_pct = max(state.maximum_drawdown_pct, drawdown)


def _force_end_close(
    state: _ReplayState,
    bars: dict[str, pd.DataFrame],
    config: CrossAssetResidualConfig,
) -> None:
    if state.position is None:
        return
    timestamp = next(iter(bars.values())).index[-1]
    _close_pair(
        state,
        timestamp,
        bars,
        math.nan,
        "end_of_data",
        (),
        config,
        price_anchor="close",
    )
