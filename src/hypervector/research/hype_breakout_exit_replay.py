"""Causal, report-only replay for HYPE breakout-specific exit policies."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReason,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    HypeExitTrade,
    HypeSide,
)
from hypervector.research.hype_breakout_exit_reporting import (
    summarize_hype_exit_replay,
)
from hypervector.research.hype_breakout_exit_validation import (
    validate_hype_exit_market,
)
from hypervector.research.hype_breakout_stop_policy import resolve_replay_stop_price


@dataclass
class _OpenPosition:
    side: HypeSide
    signal_position: int
    entry_position: int
    entry_price: float
    stop_price: float
    funding_bps: float = 0.0
    best_price: float = 0.0
    profit_stop_price: float | None = None
    maximum_favorable_excursion_bps: float = 0.0
    maximum_adverse_excursion_bps: float = 0.0


@dataclass
class _ReplayState:
    position: _OpenPosition | None = None
    pending_entry: tuple[HypeSide, int] | None = None
    pending_exit: HypeExitReason | None = None
    occupied_signals: int = 0
    reentry_blocked_side: HypeSide | None = None
    reset_blocked_signals: int = 0


def replay_hype_breakout_exits(
    market: pd.DataFrame,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig | None = None,
    *,
    entry_sides: tuple[HypeSide, ...] = ("long", "short"),
) -> HypeExitReplayReport:
    """Replay one exit policy using next-open decisions and an active venue stop."""
    cfg = config or HypeExitReplayConfig()
    _validate_entry_sides(entry_sides)
    validate_hype_exit_market(market, cfg, policy)
    state = _ReplayState()
    trades: list[HypeExitTrade] = []
    for position in range(len(market)):
        _advance_open(market, position, state, trades, policy, cfg)
        _evaluate_intrabar_stop(market, position, state, trades, policy, cfg)
        _update_excursion_and_profit_stop(market, position, state, policy)
        _schedule_close_known_actions(market, position, state, policy, cfg, entry_sides)
    _force_end_close(market, state, trades, cfg)
    return summarize_hype_exit_replay(
        policy.policy_id,
        trades,
        state.occupied_signals,
        state.reset_blocked_signals,
    )


def _advance_open(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    trades: list[HypeExitTrade],
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> None:
    _settle_funding(market, position, state)
    stop_reason = _open_stop_reason(market, position, state)
    if stop_reason is not None:
        _close(market, position, state, trades, stop_reason, policy, config)
    elif state.position is not None and state.pending_exit is not None:
        _close(market, position, state, trades, state.pending_exit, policy, config)
    state.pending_exit = None
    if state.position is None and state.pending_entry is not None:
        _open(market, position, state, config)


def _settle_funding(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
) -> None:
    opened = state.position
    if opened is None:
        return
    rate = float(market["funding_rate"].iloc[position])
    mark_ratio = float(market["open"].iloc[position]) / opened.entry_price
    sign = 1.0 if opened.side == "long" else -1.0
    opened.funding_bps += -sign * rate * mark_ratio * 10_000.0


def _open_stop_reason(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
) -> HypeExitReason | None:
    opened = state.position
    if opened is None:
        return None
    price = float(market["open"].iloc[position])
    barrier, reason = _active_stop(opened)
    crossed = price <= barrier if opened.side == "long" else price >= barrier
    return reason if crossed else None


def _open(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    config: HypeExitReplayConfig,
) -> None:
    pending = state.pending_entry
    if pending is None:
        return
    side, signal_position = pending
    raw_price = float(market["open"].iloc[position])
    entry = _adverse_price(raw_price, side, config.slippage_bps_per_side, True)
    stop = resolve_replay_stop_price(
        market,
        signal_position=signal_position,
        entry_price=entry,
        side=side,
        config=config,
    )
    state.position = _OpenPosition(
        side,
        signal_position,
        position,
        entry,
        stop,
        best_price=entry,
    )
    state.pending_entry = None


def _evaluate_intrabar_stop(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    trades: list[HypeExitTrade],
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> None:
    opened = state.position
    if opened is None:
        return
    low, high = (
        float(market["low"].iloc[position]),
        float(market["high"].iloc[position]),
    )
    barrier, reason = _active_stop(opened)
    hit = low <= barrier if opened.side == "long" else high >= barrier
    if hit:
        _close(market, position, state, trades, reason, policy, config)


def _active_stop(opened: _OpenPosition) -> tuple[float, HypeExitReason]:
    if opened.profit_stop_price is not None:
        return opened.profit_stop_price, "profit_protection"
    return opened.stop_price, "protective_stop"


def _update_excursion_and_profit_stop(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    policy: HypeExitPolicy,
) -> None:
    opened = state.position
    if opened is None:
        return
    high = float(market["high"].iloc[position])
    low = float(market["low"].iloc[position])
    _update_excursion_bar(opened, high, low)
    if policy.profit_activation_bps is None:
        return
    if opened.maximum_favorable_excursion_bps < policy.profit_activation_bps:
        return
    opened.profit_stop_price = _tightened_profit_stop(opened, policy)


def _update_excursion_bar(opened: _OpenPosition, high: float, low: float) -> None:
    if opened.side == "long":
        favorable = (high / opened.entry_price - 1.0) * 10_000.0
        adverse = (1.0 - low / opened.entry_price) * 10_000.0
        opened.best_price = max(opened.best_price, high)
    else:
        favorable = (1.0 - low / opened.entry_price) * 10_000.0
        adverse = (high / opened.entry_price - 1.0) * 10_000.0
        opened.best_price = min(opened.best_price, low)
    opened.maximum_favorable_excursion_bps = max(
        opened.maximum_favorable_excursion_bps, favorable, 0.0
    )
    opened.maximum_adverse_excursion_bps = max(
        opened.maximum_adverse_excursion_bps, adverse, 0.0
    )


def _tightened_profit_stop(
    opened: _OpenPosition,
    policy: HypeExitPolicy,
) -> float:
    floor_bps = _required_policy_value(policy.profit_floor_bps)
    giveback_bps = _required_policy_value(policy.trailing_giveback_bps)
    unit = opened.entry_price / 10_000.0
    if opened.side == "long":
        floor = opened.entry_price + floor_bps * unit
        trailing = opened.best_price - giveback_bps * unit
        return max(opened.profit_stop_price or opened.stop_price, floor, trailing)
    floor = opened.entry_price - floor_bps * unit
    trailing = opened.best_price + giveback_bps * unit
    return min(opened.profit_stop_price or opened.stop_price, floor, trailing)


def _required_policy_value(value: float | None) -> float:
    if value is None:
        raise RuntimeError("armed HYPE profit protection is incomplete")
    return value


def _schedule_close_known_actions(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
    entry_sides: tuple[HypeSide, ...],
) -> None:
    _release_reentry_block(market, position, state)
    side = _entry_side(market["entry_side"].iloc[position])
    opened = state.position
    if opened is None:
        if side in entry_sides and position + 1 < len(market):
            if side == state.reentry_blocked_side:
                state.reset_blocked_signals += 1
            else:
                state.pending_entry = (side, position)
        return
    if side is not None:
        state.occupied_signals += 1
        if config.exit_on_opposite_signal and side != opened.side:
            state.pending_exit = "opposite_strategy_intent"
            return
    state.pending_exit = _policy_exit(market, position, opened, policy)
    if state.pending_exit is None:
        state.pending_exit = _maximum_hold_exit(market, position, opened, config)


def _release_reentry_block(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
) -> None:
    blocked = state.reentry_blocked_side
    if blocked is None:
        return
    if market["structural_direction"].iloc[position] != blocked:
        state.reentry_blocked_side = None


def _maximum_hold_exit(
    market: pd.DataFrame,
    position: int,
    opened: _OpenPosition,
    config: HypeExitReplayConfig,
) -> HypeExitReason | None:
    held = position - opened.entry_position + 1
    if held < config.maximum_hold_minutes:
        return None
    if config.maximum_hold_policy == "fixed":
        return "maximum_hold"
    hard = config.hard_maximum_hold_minutes
    if hard is None:
        raise RuntimeError("validated HYPE extension lacks a hard maximum hold")
    if held >= hard:
        return "hard_maximum_hold"
    return (
        None
        if _directionally_supported(market, position, opened.side)
        else "maximum_hold"
    )


def _directionally_supported(
    market: pd.DataFrame,
    position: int,
    side: HypeSide,
) -> bool:
    row = market.iloc[position]
    structural = row["structural_direction"]
    readiness = {"metrics": {"structural_direction": structural}}
    provider = {
        "status": "observed",
        "primary_regime": row["state_5m"],
        "readiness": readiness,
    }
    canonical = provider | {
        "state_1m": row["state_1m"],
        "state_5m": row["state_5m"],
        "context_15m": row["context_15m"],
    }
    assessment = build_regime_assessment(
        side,
        {"signal_provider": provider, "canonical_regime": canonical},
    )
    return assessment["structure_stance"] == "directionally_supported"


def _policy_exit(
    market: pd.DataFrame,
    position: int,
    opened: _OpenPosition,
    policy: HypeExitPolicy,
) -> HypeExitReason | None:
    if policy.exit_on_5m_rsi_reversal and _fresh_momentum_reversal(
        market,
        position,
        opened.side,
    ):
        return "momentum_reversal_5m"
    if policy.exit_on_invalidation and market["state_5m"].iloc[position] != "BREAKOUT":
        return "breakout_invalidation"
    structural = market["structural_direction"].iloc[position]
    opposite = "short" if opened.side == "long" else "long"
    if policy.exit_on_reversal and structural == opposite:
        return "structural_reversal"
    return None


def _fresh_momentum_reversal(
    market: pd.DataFrame,
    position: int,
    side: HypeSide,
) -> bool:
    """Return whether a newly completed 5m RSI cross opposes the open side."""
    if position < 1:
        return False
    current = _momentum_gap(market, position)
    previous = _momentum_gap(market, position - 1)
    if current is None or previous is None:
        return False
    if side == "long":
        return current < 0.0 <= previous
    return current > 0.0 >= previous


def _momentum_gap(market: pd.DataFrame, position: int) -> float | None:
    rsi = float(market["regime_5m_rsi"].iloc[position])
    signal = float(market["regime_5m_rsi_ema"].iloc[position])
    if not math.isfinite(rsi) or not math.isfinite(signal):
        return None
    return rsi - signal


def _close(
    market: pd.DataFrame,
    position: int,
    state: _ReplayState,
    trades: list[HypeExitTrade],
    reason: HypeExitReason,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> None:
    opened = state.position
    if opened is None:
        raise RuntimeError("HYPE exit replay cannot close a flat lifecycle")
    raw_exit = _raw_exit_price(market, position, opened, reason)
    _update_excursion_price(opened, raw_exit)
    exit_price = _adverse_price(
        raw_exit, opened.side, config.slippage_bps_per_side, False
    )
    trades.append(_trade(market, position, opened, exit_price, reason, config))
    if reason == "profit_protection" and policy.reentry_requires_structural_reset:
        state.reentry_blocked_side = opened.side
    state.position = None
    state.pending_exit = None


def _raw_exit_price(
    market: pd.DataFrame,
    position: int,
    opened: _OpenPosition,
    reason: HypeExitReason,
) -> float:
    bar_open = float(market["open"].iloc[position])
    if reason not in {"protective_stop", "profit_protection"}:
        return bar_open
    barrier = (
        opened.profit_stop_price if reason == "profit_protection" else opened.stop_price
    )
    if barrier is None:
        raise RuntimeError("HYPE profit-protection exit is missing its stop")
    if opened.side == "long":
        return min(barrier, bar_open)
    return max(barrier, bar_open)


def _update_excursion_price(opened: _OpenPosition, price: float) -> None:
    _update_excursion_bar(opened, price, price)


def _trade(
    market: pd.DataFrame,
    position: int,
    opened: _OpenPosition,
    exit_price: float,
    reason: HypeExitReason,
    config: HypeExitReplayConfig,
) -> HypeExitTrade:
    sign = 1.0 if opened.side == "long" else -1.0
    gross = sign * (exit_price / opened.entry_price - 1.0) * 10_000.0
    fees = config.fee_bps_per_side * (1.0 + exit_price / opened.entry_price)
    net = gross - fees + opened.funding_bps
    return HypeExitTrade(
        opened.side,
        market.index[opened.signal_position].isoformat(),
        market.index[opened.entry_position].isoformat(),
        market.index[position].isoformat(),
        opened.entry_price,
        exit_price,
        opened.stop_price,
        gross,
        fees,
        opened.funding_bps,
        net,
        position - opened.entry_position,
        opened.maximum_favorable_excursion_bps,
        opened.maximum_adverse_excursion_bps,
        reason,
    )


def _force_end_close(
    market: pd.DataFrame,
    state: _ReplayState,
    trades: list[HypeExitTrade],
    config: HypeExitReplayConfig,
) -> None:
    if state.position is None:
        return
    position = len(market) - 1
    raw_close = float(market["close"].iloc[position])
    opened = state.position
    _update_excursion_price(opened, raw_close)
    exit_price = _adverse_price(
        raw_close, opened.side, config.slippage_bps_per_side, False
    )
    trades.append(_trade(market, position, opened, exit_price, "end_of_data", config))
    state.position = None


def _adverse_price(
    price: float,
    side: HypeSide,
    slippage_bps: float,
    entering: bool,
) -> float:
    fraction = slippage_bps / 10_000.0
    higher = (side == "long") == entering
    return price * (1.0 + fraction if higher else 1.0 - fraction)


def _entry_side(value: object) -> HypeSide | None:
    if value in {None, "", "neutral"} or pd.isna(value):
        return None
    if value == "long":
        return "long"
    if value == "short":
        return "short"
    raise ValueError("HYPE entry_side must be long, short, or empty")


def _validate_entry_sides(entry_sides: tuple[HypeSide, ...]) -> None:
    if (
        not entry_sides
        or len(set(entry_sides)) != len(entry_sides)
        or not set(entry_sides) <= {"long", "short"}
    ):
        raise ValueError("entry_sides must contain unique supported sides")
