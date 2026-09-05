"""Causal finite-depth lifecycles for prospective HIP-3 shadow onsets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean
from typing import cast

import pandas as pd

from hypervector.research.hip3_shadow_lifecycle_inputs import (
    INTERVAL_MS,
    Hip3ShadowMark,
    Hip3ShadowLifecycleInputs,
    mark_path_resolved,
    prepare_shadow_lifecycle_inputs,
)
from hypervector.research.hip3_shadow_lifecycle_exits import (
    Hip3ShadowExitEvent,
    opposite_entry_exit_time,
    select_shadow_exit_event,
)
from hypervector.research.hip3_shadow_lifecycle_models import (
    Hip3ShadowCensoredLifecycle,
    Hip3ShadowLifecycle,
    Hip3ShadowLifecycleConfig,
)
from hypervector.research.hip3_shadow_lifecycle_reporting import (
    build_shadow_lifecycle_report,
)
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowBook,
    Hip3ShadowDecision,
    first_shadow_book_at_or_after,
)


@dataclass(frozen=True)
class _DepthFill:
    price: float
    quantity: float
    quote_usd: float


def build_hip3_shadow_lifecycle_replay(
    *,
    decision_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    candles: pd.DataFrame,
    mark_rows: Sequence[Mapping[str, object]],
    funding_rows: pd.DataFrame,
    config: Hip3ShadowLifecycleConfig,
    profit_lock_bars: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Replay one exact no-authority route under nominal and stress costs."""
    inputs = prepare_shadow_lifecycle_inputs(
        decision_rows=decision_rows,
        book_rows=book_rows,
        candles=candles,
        mark_rows=mark_rows,
        funding_rows=funding_rows,
        config=config,
    )
    nominal = _simulate_inputs(inputs, profit_lock_bars, config, stress=False)
    stress = _simulate_inputs(inputs, profit_lock_bars, config, stress=True)
    return build_shadow_lifecycle_report(
        config,
        inputs.decisions,
        inputs.books,
        inputs.marks,
        inputs.signal_bars,
        inputs.funding_evidence,
        nominal,
        stress,
    )


def _simulate_inputs(
    inputs: Hip3ShadowLifecycleInputs,
    profit_lock_bars: pd.DataFrame | None,
    config: Hip3ShadowLifecycleConfig,
    stress: bool,
) -> dict[str, object]:
    return _simulate(
        inputs.decisions,
        inputs.books,
        inputs.marks,
        inputs.signals,
        inputs.publication,
        inputs.funding,
        profit_lock_bars,
        config,
        stress,
    )


def _simulate(
    decisions: Sequence[Hip3ShadowDecision],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Hip3ShadowMark],
    signals: pd.DataFrame,
    publication: Mapping[int, int],
    funding: pd.DataFrame,
    profit_lock_bars: pd.DataFrame | None,
    config: Hip3ShadowLifecycleConfig,
    stress: bool,
) -> dict[str, object]:
    completed: list[Hip3ShadowLifecycle] = []
    censored: list[Hip3ShadowCensoredLifecycle] = []
    known_busy_until = -1
    unresolved_until = -1
    unresolved_for_remainder = False
    suppressed = 0
    for decision in decisions:
        if decision.side not in config.entry_sides:
            continue
        blocked = _state_censor(decision, unresolved_for_remainder, unresolved_until)
        if blocked is not None:
            censored.append(blocked)
            continue
        if decision.observed_at_ms < known_busy_until:
            suppressed += 1
            continue
        result = _one_lifecycle(
            decision,
            decisions,
            books,
            marks,
            signals,
            publication,
            funding,
            profit_lock_bars,
            config,
            stress,
        )
        if isinstance(result, Hip3ShadowLifecycle):
            completed.append(result)
            known_busy_until = _busy_until(result)
        else:
            censored.append(result)
            if result.entry_time_ms is not None:
                if result.route_state_resolved_time_ms is None:
                    unresolved_for_remainder = True
                else:
                    unresolved_until = result.route_state_resolved_time_ms
    return _summary(completed, censored, suppressed)


def _busy_until(result: Hip3ShadowLifecycle) -> int:
    """Consume an opposite close signal without allowing same-cycle reversal."""
    return result.exit_time_ms + int(result.exit_reason == "opposite_strategy_intent")


def _state_censor(
    decision: Hip3ShadowDecision,
    unresolved_for_remainder: bool,
    unresolved_until: int,
) -> Hip3ShadowCensoredLifecycle | None:
    if not unresolved_for_remainder and decision.observed_at_ms >= unresolved_until:
        return None
    return _censored(
        decision,
        "portfolio_state_unresolved",
        route_state_resolved_time_ms=None
        if unresolved_for_remainder
        else unresolved_until,
    )


def _one_lifecycle(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Hip3ShadowMark],
    signals: pd.DataFrame,
    publication: Mapping[int, int],
    funding: pd.DataFrame,
    profit_lock_bars: pd.DataFrame | None,
    config: Hip3ShadowLifecycleConfig,
    stress: bool,
) -> Hip3ShadowLifecycle | Hip3ShadowCensoredLifecycle:
    entry_book = _book_at(books, decision.observed_at_ms, config)
    if entry_book is None:
        return _censored(decision, "entry_book_unresolved")
    entry = _entry_fill(entry_book, decision.side, config.notional_usd)
    if entry is None:
        return _censored(decision, "entry_depth_incomplete")
    stop = _stop_price(decision, signals, entry.price, config)
    event = _select_lifecycle_exit(
        decision,
        decisions,
        entry_book,
        marks,
        signals,
        publication,
        stop,
        entry.price,
        profit_lock_bars,
        config,
    )
    if event is None:
        return _post_entry_censor(decision, entry_book, "exit_event_censored")
    return _resolve_lifecycle_exit(
        decision, entry_book, entry, stop, event, books, marks, funding, config, stress
    )


def _select_lifecycle_exit(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    entry_book: Hip3ShadowBook,
    marks: Sequence[Hip3ShadowMark],
    signals: pd.DataFrame,
    publication: Mapping[int, int],
    stop: float,
    entry_price: float,
    profit_lock_bars: pd.DataFrame | None,
    config: Hip3ShadowLifecycleConfig,
) -> Hip3ShadowExitEvent | None:
    return select_shadow_exit_event(
        decision,
        entry_book,
        marks,
        signals,
        publication,
        stop,
        entry_price,
        profit_lock_bars,
        config,
        opposite_entry_exit_time(decision, decisions, entry_book, config),
    )


def _resolve_lifecycle_exit(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    entry: _DepthFill,
    stop: float,
    event: Hip3ShadowExitEvent,
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Hip3ShadowMark],
    funding: pd.DataFrame,
    config: Hip3ShadowLifecycleConfig,
    stress: bool,
) -> Hip3ShadowLifecycle | Hip3ShadowCensoredLifecycle:
    exit_book, close = _event_exit_fill(books, event, decision, entry, config)
    resolved_time = exit_book.recv_ts_ms if close is not None else None
    if not mark_path_resolved(
        marks,
        entry_book.recv_ts_ms,
        event.timestamp_ms,
        config.maximum_mark_gap_ms,
    ):
        return _post_entry_censor(
            decision,
            entry_book,
            "mark_path_unresolved",
            route_state_resolved_time_ms=resolved_time,
        )
    if exit_book is None:
        return _post_entry_censor(decision, entry_book, "exit_book_unresolved")
    if close is None:
        return _post_entry_censor(decision, entry_book, "exit_depth_incomplete")
    return _lifecycle(
        decision,
        entry_book,
        entry,
        exit_book,
        close,
        stop,
        event,
        funding,
        config,
        stress,
    )


def _event_exit_fill(
    books: Sequence[Hip3ShadowBook],
    event: Hip3ShadowExitEvent,
    decision: Hip3ShadowDecision,
    entry: _DepthFill,
    config: Hip3ShadowLifecycleConfig,
) -> tuple[Hip3ShadowBook | None, _DepthFill | None]:
    exit_book = _book_at(books, event.timestamp_ms, config)
    close = _exit_fill(exit_book, decision.side, entry.quantity) if exit_book else None
    return exit_book, close


def _book_at(
    books: Sequence[Hip3ShadowBook],
    timestamp_ms: int,
    config: Hip3ShadowLifecycleConfig,
) -> Hip3ShadowBook | None:
    _status, book = first_shadow_book_at_or_after(
        books,
        [value.recv_ts_ms for value in books],
        timestamp_ms,
        config.maximum_book_lateness_ms,
    )
    return book


def _entry_fill(
    book: Hip3ShadowBook, side: str, notional_usd: float
) -> _DepthFill | None:
    levels = book.asks if side == "long" else book.bids
    quantity = notional_usd / levels[0][0]
    return _depth_fill(levels, quantity)


def _exit_fill(book: Hip3ShadowBook, side: str, quantity: float) -> _DepthFill | None:
    return _depth_fill(book.bids if side == "long" else book.asks, quantity)


def _depth_fill(
    levels: Sequence[tuple[float, float]], quantity: float
) -> _DepthFill | None:
    remaining = quantity
    quote = 0.0
    for price, available in levels:
        filled = min(remaining, available)
        quote += filled * price
        remaining -= filled
        if remaining <= 1e-12:
            return _DepthFill(quote / quantity, quantity, quote)
    return None


def _stop_price(
    decision: Hip3ShadowDecision,
    signals: pd.DataFrame,
    entry_price: float,
    config: Hip3ShadowLifecycleConfig,
) -> float:
    if config.fixed_stop_bps is not None:
        distance = config.fixed_stop_bps / 10_000.0
        return entry_price * (
            1.0 - distance if decision.side == "long" else 1.0 + distance
        )
    position = pd.Timestamp(
        decision.decision_time_ms - INTERVAL_MS, unit="ms", tz="UTC"
    )
    signal_stop = float(signals.loc[position, "stop_price"])
    distance = config.signal_config.maximum_stop_bps / 10_000.0
    fixed = entry_price * (
        1.0 - distance if decision.side == "long" else 1.0 + distance
    )
    return (
        max(signal_stop, fixed) if decision.side == "long" else min(signal_stop, fixed)
    )


def _lifecycle(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    entry: _DepthFill,
    exit_book: Hip3ShadowBook,
    close: _DepthFill,
    stop: float,
    event: Hip3ShadowExitEvent,
    funding: pd.DataFrame,
    config: Hip3ShadowLifecycleConfig,
    stress: bool,
) -> Hip3ShadowLifecycle:
    direction = 1.0 if decision.side == "long" else -1.0
    gross = direction * (close.quote_usd - entry.quote_usd)
    fees = (entry.quote_usd + close.quote_usd) * config.fee_bps_per_side / 10_000.0
    rate = _funding_rate(funding, entry_book.recv_ts_ms, exit_book.recv_ts_ms)
    funding_cash = -direction * entry.quote_usd * rate
    friction_bps = config.residual_latency_bps_per_side + (
        config.stress_extra_bps_per_side if stress else 0.0
    )
    modeled = (entry.quote_usd + close.quote_usd) * friction_bps / 10_000.0
    net = gross - fees + funding_cash - modeled
    gross_bps = gross / entry.quote_usd * 10_000.0
    return Hip3ShadowLifecycle(
        cast(str, decision.side),
        decision.decision_time_ms,
        decision.observed_at_ms,
        entry_book.recv_ts_ms,
        exit_book.recv_ts_ms,
        entry.price,
        close.price,
        stop,
        event.stop_trigger_time_ms,
        event.reason,
        entry.quantity,
        entry.quote_usd,
        gross,
        fees,
        funding_cash,
        modeled,
        net,
        gross_bps,
        net / entry.quote_usd * 10_000.0,
    )


def _funding_rate(funding: pd.DataFrame, start_ms: int, end_ms: int) -> float:
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC")
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC")
    expected = pd.date_range(
        start.floor("h") + pd.Timedelta(hours=1), end.floor("h"), freq="h"
    )
    if not expected.isin(funding.index).all():
        raise ValueError("HIP-3 lifecycle funding coverage is incomplete")
    selected = funding.loc[
        (funding.index > start) & (funding.index <= end),
        "funding_rate",
    ]
    return float(selected.sum())


def _summary(
    completed: Sequence[Hip3ShadowLifecycle],
    censored: Sequence[Hip3ShadowCensoredLifecycle],
    suppressed: int,
) -> dict[str, object]:
    return {
        "completed_lifecycles": len(completed),
        "censored_lifecycles": len(censored),
        "suppressed_overlapping_onsets": suppressed,
        **_economics(completed),
        "by_side": {
            side: _side_summary(completed, censored, side) for side in ("long", "short")
        },
        "lifecycles": [row.to_dict() for row in completed],
        "censored": [row.to_dict() for row in censored],
    }


def _economics(completed: Sequence[Hip3ShadowLifecycle]) -> dict[str, object]:
    pnl = [value.net_pnl_usd for value in completed]
    wins = [value for value in pnl if value > 0.0]
    losses = [value for value in pnl if value < 0.0]
    return {
        "wins": len(wins),
        "losses": len(losses),
        "net_pnl_usd": sum(pnl),
        "mean_net_return_bps": mean([row.net_return_bps for row in completed])
        if completed
        else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "net_without_largest_winner_usd": sum(pnl) - max(wins) if wins else None,
    }


def _side_summary(
    completed: Sequence[Hip3ShadowLifecycle],
    censored: Sequence[Hip3ShadowCensoredLifecycle],
    side: str,
) -> dict[str, object]:
    selected = [row for row in completed if row.side == side]
    return {
        "lifecycles": len(selected),
        "censored_lifecycles": sum(row.side == side for row in censored),
        **_economics(selected),
    }


def _censored(
    decision: Hip3ShadowDecision,
    reason: str,
    *,
    route_state_resolved_time_ms: int | None = None,
) -> Hip3ShadowCensoredLifecycle:
    return Hip3ShadowCensoredLifecycle(
        cast(str, decision.side),
        decision.decision_time_ms,
        reason,
        route_state_resolved_time_ms=route_state_resolved_time_ms,
    )


def _post_entry_censor(
    decision: Hip3ShadowDecision,
    entry_book: Hip3ShadowBook,
    reason: str,
    *,
    route_state_resolved_time_ms: int | None = None,
) -> Hip3ShadowCensoredLifecycle:
    return Hip3ShadowCensoredLifecycle(
        cast(str, decision.side),
        decision.decision_time_ms,
        reason,
        entry_time_ms=entry_book.recv_ts_ms,
        route_state_resolved_time_ms=route_state_resolved_time_ms,
    )
