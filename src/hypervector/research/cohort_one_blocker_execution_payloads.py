"""Pricing and telemetry payloads for one-blocker execution replay."""

from __future__ import annotations

from collections.abc import Sequence
import math

from hypervector.research.cohort_one_blocker_execution_contract import (
    OneBlockerExecutionContract,
)
from hypervector.research.cohort_one_blocker_execution_types import Book
from hypervector.research.cohort_signal_candidates import SignalCandidate

_ENTRY_FEATURE_KEYS = (
    "primary_regime",
    "state_1m",
    "state_5m",
    "context_15m",
    "prior_state_5m",
    "structural_direction",
    "entry_feature_authority",
    "entry_feature_provenance",
    "entry_feature_status",
    "breakout_onset",
    "breakout_volume_ratio",
    "breakout_clearance_20m_bps",
    "current_bbwp_percentile",
    "prior_bbwp_min_15m",
    "regime_strength",
    "confidence",
    "state_1m_alignment",
    "context_15m_alignment",
    "directional_bar_body_bps",
    "directional_return_5m_bps",
    "directional_return_15m_bps",
    "directional_return_60m_bps",
    "ema_gap_directional_bps",
    "rsi_directional_distance",
)


def direction(candidate: SignalCandidate) -> float:
    """Return the signed direction for a directional candidate."""
    if candidate.side == "long":
        return 1.0
    if candidate.side == "short":
        return -1.0
    raise ValueError("execution candidate requires a direction")


def entry_level(book: Book, trade_direction: float) -> tuple[float, float]:
    """Return the adverse top-of-book entry price and capacity."""
    if trade_direction > 0.0:
        return book.ask_price, book.ask_size
    return book.bid_price, book.bid_size


def exit_level(book: Book, trade_direction: float) -> tuple[float, float]:
    """Return the adverse top-of-book exit price and capacity."""
    if trade_direction > 0.0:
        return book.bid_price, book.bid_size
    return book.ask_price, book.ask_size


def attempt_base(candidate: SignalCandidate, context: Book) -> dict[str, object]:
    """Build fields shared by pending, failed, and resolved attempts."""
    values: dict[str, object] = {
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "decision_time_ms": candidate.decision_time_ms,
        "available_time_ms": candidate.available_time_ms,
        "directional_opi": direction(candidate) * context.opi,
        "context_book_time_ms": context.recv_ts_ms,
    }
    if candidate.source_run_id is not None:
        values["source_run_id"] = candidate.source_run_id
    entry_features = _entry_features(candidate)
    if entry_features:
        values["entry_features"] = entry_features
    return values


def _entry_features(candidate: SignalCandidate) -> dict[str, object]:
    features: dict[str, object] = {}
    for name in _ENTRY_FEATURE_KEYS:
        if name not in candidate.metrics:
            continue
        value = candidate.metrics[name]
        if isinstance(value, (str, bool)):
            features[name] = value
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            features[name] = value
        else:
            raise ValueError(f"entry feature {name} must be a finite scalar")
    return features


def pending_attempt(
    base: dict[str, object],
    candidate: SignalCandidate,
    entry: Book,
    latest: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry_price: float,
    position_size: float,
    deadline: int,
    contract: OneBlockerExecutionContract,
) -> dict[str, object]:
    """Describe a causally pending position without fabricating an exit."""
    trade_direction = direction(candidate)
    exit_price, exit_size = exit_level(latest, trade_direction)
    gross, fee, funding_bps, net = _returns(
        entry_price,
        exit_price,
        position_size,
        entry.recv_ts_ms,
        latest.recv_ts_ms,
        trade_direction,
        funding,
        contract,
    )
    path = _path_returns(books, entry, latest, entry_price, trade_direction)
    return base | {
        "status": "exit_pending",
        "entry_time_ms": entry.recv_ts_ms,
        "entry_price": entry_price,
        "deadline_time_ms": deadline,
        "latest_book_time_ms": latest.recv_ts_ms,
        "elapsed_ms": latest.recv_ts_ms - entry.recv_ts_ms,
        "remaining_ms": deadline - latest.recv_ts_ms,
        "current_gross_return_bps": gross,
        "current_fee_bps": fee,
        "current_funding_bps": funding_bps,
        "current_estimated_net_return_bps": net,
        "mfe_bps": max(path),
        "mae_bps": min(path),
        "current_exit_top_level_capacity": exit_size + 1e-12 >= position_size,
    }


def execution_payload(
    candidate: SignalCandidate,
    context: Book,
    books: Sequence[Book],
    funding: Sequence[tuple[int, float]],
    entry: Book,
    exit_book: Book,
    entry_price: float,
    exit_price: float,
    position_size: float,
    exit_reason: str,
    contract: OneBlockerExecutionContract,
) -> dict[str, object]:
    """Build a resolved execution payload with fees, funding, MFE, and MAE."""
    trade_direction = direction(candidate)
    gross_bps, fee_bps, funding_bps, net_bps = _returns(
        entry_price,
        exit_price,
        position_size,
        entry.recv_ts_ms,
        exit_book.recv_ts_ms,
        trade_direction,
        funding,
        contract,
    )
    path = _path_returns(books, entry, exit_book, entry_price, trade_direction)
    return {
        **attempt_base(candidate, context),
        "status": "resolved",
        "entry_time_ms": entry.recv_ts_ms,
        "exit_time_ms": exit_book.recv_ts_ms,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "position_size": position_size,
        "gross_return_bps": gross_bps,
        "fee_bps": fee_bps,
        "funding_bps": funding_bps,
        "net_return_bps": net_bps,
        "simulated_net_pnl_usd": contract.notional_usd * net_bps / 10_000.0,
        "mfe_bps": max(path),
        "mae_bps": min(path),
        "crossed_stop_proxy": exit_reason == "stop_proxy",
    }


def _returns(
    entry_price: float,
    exit_price: float,
    position_size: float,
    entry_time_ms: int,
    exit_time_ms: int,
    trade_direction: float,
    funding: Sequence[tuple[int, float]],
    contract: OneBlockerExecutionContract,
) -> tuple[float, float, float, float]:
    gross_bps = trade_direction * (exit_price / entry_price - 1.0) * 10_000.0
    exit_notional = position_size * exit_price
    fees_usd = contract.taker_fee_rate * (contract.notional_usd + exit_notional)
    fee_bps = fees_usd / contract.notional_usd * 10_000.0
    funding_bps = _funding_bps(funding, entry_time_ms, exit_time_ms, trade_direction)
    return gross_bps, fee_bps, funding_bps, gross_bps - fee_bps + funding_bps


def _funding_bps(
    events: Sequence[tuple[int, float]],
    start_ms: int,
    end_ms: int,
    trade_direction: float,
) -> float:
    return (
        -trade_direction
        * sum(rate for time_ms, rate in events if start_ms < time_ms <= end_ms)
        * 10_000.0
    )


def _path_returns(
    books: Sequence[Book],
    entry: Book,
    exit_book: Book,
    entry_price: float,
    trade_direction: float,
) -> list[float]:
    return [
        trade_direction
        * (exit_level(book, trade_direction)[0] / entry_price - 1.0)
        * 10_000.0
        for book in books
        if entry.recv_ts_ms <= book.recv_ts_ms <= exit_book.recv_ts_ms
    ]
