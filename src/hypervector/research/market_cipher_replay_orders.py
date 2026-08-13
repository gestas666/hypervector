"""Entry selection and pending exits for Market Cipher replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.market_cipher_replay_lifecycle import (
    close_position_leg,
    update_replay_drawdown,
)
from hypervector.research.market_cipher_replay_models import (
    MarketCipherReplayConfig,
    ReplayRejection,
)
from hypervector.research.market_cipher_replay_risk import (
    adverse_price,
    candidate_entry_price,
    candidate_stop_terms,
    position_liquidation_price,
    remaining_margin,
    stop_anchor_is_adverse,
)
from hypervector.research.market_cipher_replay_state import (
    ReplayCandidate,
    ReplayOpenPosition,
    ReplayState,
)


def execute_pending_exits(
    state: ReplayState,
    available: dict[str, pd.Series],
    timestamp: pd.Timestamp,
    config: MarketCipherReplayConfig,
) -> None:
    """Execute close-known trailing decisions at the next symbol open."""
    for symbol in sorted(tuple(state.positions)):
        opened = state.positions[symbol]
        if opened.pending_exit is None or symbol not in available:
            continue
        price = adverse_price(
            float(available[symbol]["open"]),
            opened.candidate.direction,
            config,
            entering=False,
        )
        close_position_leg(
            state, opened, timestamp, price, 1.0, opened.pending_exit, config
        )


def fill_replay_candidates(
    state: ReplayState,
    candidates: list[ReplayCandidate],
    config: MarketCipherReplayConfig,
) -> None:
    """Rank simultaneous decisions and fill all portfolio-admissible entries."""
    ordered = sorted(
        candidates,
        key=lambda item: (-item.score, item.symbol, item.candidate),
    )
    seen: set[str] = set()
    for candidate in ordered:
        if candidate.symbol in seen:
            _reject(state, candidate, "duplicate_symbol_candidate")
            continue
        seen.add(candidate.symbol)
        reason = _portfolio_rejection(state, candidate, config)
        if reason is not None:
            _reject(state, candidate, reason)
            continue
        state.positions[candidate.symbol] = _open_position(state, candidate, config)
        state.maximum_concurrent_positions = max(
            state.maximum_concurrent_positions, len(state.positions)
        )


def _portfolio_rejection(
    state: ReplayState,
    candidate: ReplayCandidate,
    config: MarketCipherReplayConfig,
) -> str | None:
    if candidate.symbol in state.positions:
        return "symbol_position_open"
    if len(state.positions) >= config.maximum_concurrent_positions:
        return "portfolio_capacity"
    if candidate.risk_multiplier > config.maximum_signal_risk_multiplier:
        return "risk_multiplier_exceeds_configured_max"
    risk = _candidate_risk(state, candidate, config)
    open_risk = sum(position.risk_budget for position in state.positions.values())
    if open_risk + risk > state.equity * config.maximum_portfolio_risk_fraction:
        return "portfolio_risk_cap"
    entry = candidate_entry_price(candidate, config)
    if not stop_anchor_is_adverse(candidate, entry):
        return "stop_anchor_crossed_at_entry"
    stop, _ = candidate_stop_terms(candidate, entry, config)
    margin = (risk / abs(entry - stop)) * entry / config.leverage
    used = sum(remaining_margin(position) for position in state.positions.values())
    if used + margin > state.equity:
        return "insufficient_isolated_margin"
    return None


def _open_position(
    state: ReplayState,
    candidate: ReplayCandidate,
    config: MarketCipherReplayConfig,
) -> ReplayOpenPosition:
    entry = candidate_entry_price(candidate, config)
    stop, distance_bps = candidate_stop_terms(candidate, entry, config)
    risk = _candidate_risk(state, candidate, config)
    quantity = risk / abs(entry - stop)
    margin = quantity * entry / config.leverage
    fee = quantity * entry * config.entry_fee_rate
    equity_before = state.equity
    state.equity -= fee
    opened = ReplayOpenPosition(
        candidate,
        candidate.entry_time,
        entry,
        stop,
        distance_bps,
        quantity,
        quantity,
        margin,
        risk,
        fee,
        equity_before,
        0.0,
        fees=fee,
    )
    opened.initial_liquidation_price = position_liquidation_price(opened, config)
    update_replay_drawdown(state, state.equity)
    return opened


def _candidate_risk(
    state: ReplayState,
    candidate: ReplayCandidate,
    config: MarketCipherReplayConfig,
) -> float:
    return state.equity * config.risk_fraction * candidate.risk_multiplier


def _reject(state: ReplayState, candidate: ReplayCandidate, reason: str) -> None:
    state.rejections.append(
        ReplayRejection(
            candidate.signal_time.isoformat(),
            candidate.symbol,
            candidate.candidate,
            reason,
        )
    )
