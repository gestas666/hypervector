"""Causal report-only lifecycles for the BRENTOIL oil-shock shadow."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from statistics import mean
from typing import cast

from hypervector.data.hl_events import AssetContextEvent
from hypervector.live.brentoil_oil_shock_shadow import (
    BRENTOIL_OIL_SHOCK_PROFILE_ID,
    BRENTOIL_OIL_SHOCK_PROVIDER_ID,
    BRENTOIL_OIL_SHOCK_SYMBOL,
    BRENTOIL_SIGNAL_SOURCE,
)
from hypervector.research.brentoil_oil_shock_lifecycle_inputs import (
    mapping,
    reconcile_candles,
    unresolved_prospective_boundaries,
    validated_decisions,
    validated_marks,
)
from hypervector.research.brentoil_oil_shock_lifecycle_models import (
    BrentoilOilShockLifecycleConfig,
    ExitEvent,
    Fill,
    Lifecycle,
    Mark,
    positive_integer,
)
from hypervector.research.hip3_prospective_path_audit import hip3_bar_path_quality
from hypervector.research.hip3_shadow_signal_markouts import (
    Hip3ShadowBook,
    Hip3ShadowDecision,
    first_shadow_book_at_or_after,
    validated_shadow_books,
)


def build_brentoil_oil_shock_lifecycle_report(
    *,
    decision_rows: Sequence[Mapping[str, object]],
    candle_rows: Sequence[Mapping[str, object]],
    book_rows: Sequence[Mapping[str, object]],
    marks: Sequence[AssetContextEvent],
    observed_at_ms: int,
    config: BrentoilOilShockLifecycleConfig,
) -> dict[str, object]:
    """Replay source-correct eligible onsets under exact strategy exits."""
    positive_integer(observed_at_ms, "observed at")
    decisions = validated_decisions(decision_rows, observed_at_ms)
    prospective = reconcile_candles(decision_rows, candle_rows, observed_at_ms)
    unresolved_boundaries = unresolved_prospective_boundaries(
        candle_rows, observed_at_ms
    )
    books = validated_shadow_books(book_rows, config)
    mark_path = validated_marks(marks, observed_at_ms)
    nominal = _simulate(
        decisions,
        prospective,
        unresolved_boundaries,
        books,
        mark_path,
        observed_at_ms,
        config,
        stress=False,
    )
    stress = _simulate(
        decisions,
        prospective,
        unresolved_boundaries,
        books,
        mark_path,
        observed_at_ms,
        config,
        stress=True,
    )
    return _report(
        decision_rows, candle_rows, books, mark_path, nominal, stress, config
    )


def _simulate(
    decisions: Sequence[Hip3ShadowDecision],
    prospective: set[int],
    unresolved_boundaries: set[int],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Mark],
    observed_at_ms: int,
    config: BrentoilOilShockLifecycleConfig,
    *,
    stress: bool,
) -> dict[str, object]:
    resolved: list[Lifecycle] = []
    censored: list[dict[str, object]] = []
    busy_until = -1
    state_unresolved = False
    suppressed = 0
    for decision in decisions:
        if state_unresolved:
            censored.append(_censored(decision, "portfolio_state_unresolved"))
        elif decision.observed_at_ms < busy_until:
            suppressed += 1
        elif decision.decision_time_ms not in prospective:
            censored.append(_censored(decision, "source_candle_not_prospective"))
        else:
            result = _one_lifecycle(
                decision,
                decisions,
                unresolved_boundaries,
                books,
                marks,
                observed_at_ms,
                config,
                stress,
            )
            if isinstance(result, Lifecycle):
                resolved.append(result)
                busy_until = result.exit_time_ms + 1
            else:
                censored.append(result)
                state_unresolved = result.get("entry_time_ms") is not None
    return _simulation_report(resolved, censored, suppressed)


def _one_lifecycle(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    unresolved_boundaries: set[int],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Mark],
    observed_at_ms: int,
    config: BrentoilOilShockLifecycleConfig,
    stress: bool,
) -> Lifecycle | dict[str, object]:
    entry_book = _book_at(books, decision.observed_at_ms, config)
    if entry_book is None:
        return _censored(decision, "entry_book_unresolved")
    entry = _entry_fill(entry_book, decision.side, config.notional_usd)
    if entry is None:
        return _censored(decision, "entry_depth_incomplete")
    event = _exit_event(decision, decisions, entry, marks, observed_at_ms, config)
    if event is None:
        return _censored(decision, "right_censored", entry.timestamp_ms)
    if _decision_path_unresolved(unresolved_boundaries, entry.timestamp_ms, event):
        return _censored(decision, "decision_path_unresolved", entry.timestamp_ms)
    if not _mark_path_resolved(marks, entry.timestamp_ms, event.timestamp_ms, config):
        return _censored(decision, "mark_path_unresolved", entry.timestamp_ms)
    exit_book = _book_at(books, event.timestamp_ms, config)
    if exit_book is None:
        return _censored(decision, "exit_book_unresolved", entry.timestamp_ms)
    close = _exit_fill(exit_book, decision.side, entry.quantity)
    if close is None:
        return _censored(decision, "exit_depth_incomplete", entry.timestamp_ms)
    return _lifecycle(decision, entry, close, event, config, stress)


def _decision_path_unresolved(
    boundaries: set[int], entry_ms: int, event: ExitEvent
) -> bool:
    return any(entry_ms < boundary <= event.timestamp_ms for boundary in boundaries)


def _exit_event(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    entry: Fill,
    marks: Sequence[Mark],
    observed_at_ms: int,
    config: BrentoilOilShockLifecycleConfig,
) -> ExitEvent | None:
    target, stop = _barriers(decision.side, entry.price, config)
    deadline = entry.timestamp_ms + config.maximum_hold_ms
    candidates: list[ExitEvent] = []
    for mark in marks:
        if not entry.timestamp_ms <= mark.timestamp_ms <= min(deadline, observed_at_ms):
            continue
        reason = _barrier_reason(decision.side, mark.price, target, stop)
        if reason is not None:
            candidates.append(ExitEvent(reason, mark.timestamp_ms))
            break
    opposite = _opposite_time(decision, decisions, entry.timestamp_ms)
    if opposite is not None and opposite <= observed_at_ms:
        candidates.append(ExitEvent("opposite_signal", opposite))
    if deadline <= observed_at_ms:
        candidates.append(ExitEvent("max_hold", deadline))
    return min(candidates, key=lambda value: value.timestamp_ms) if candidates else None


def _lifecycle(
    decision: Hip3ShadowDecision,
    entry: Fill,
    close: Fill,
    event: ExitEvent,
    config: BrentoilOilShockLifecycleConfig,
    stress: bool,
) -> Lifecycle:
    direction = 1.0 if decision.side == "long" else -1.0
    gross = direction * (close.quote_usd - entry.quote_usd)
    turnover = entry.quote_usd + close.quote_usd
    fees = turnover * config.fee_bps_per_side / 10_000.0
    residual_bps = (
        config.stress_residual_bps_per_side
        if stress
        else config.nominal_residual_bps_per_side
    )
    residual = turnover * residual_bps / 10_000.0
    net = gross - fees - residual
    target, stop = _barriers(decision.side, entry.price, config)
    return Lifecycle(
        decision.side,
        decision.decision_time_ms,
        decision.observed_at_ms,
        entry.timestamp_ms,
        event.timestamp_ms,
        close.timestamp_ms,
        event.reason,
        entry.price,
        close.price,
        target,
        stop,
        entry.quantity,
        entry.quote_usd,
        gross,
        fees,
        residual,
        net,
        net / entry.quote_usd * 10_000.0,
    )


def _book_at(
    books: Sequence[Hip3ShadowBook],
    timestamp_ms: int,
    config: BrentoilOilShockLifecycleConfig,
) -> Hip3ShadowBook | None:
    _status, book = first_shadow_book_at_or_after(
        books,
        [value.recv_ts_ms for value in books],
        timestamp_ms,
        config.maximum_book_lateness_ms,
    )
    return book


def _entry_fill(book: Hip3ShadowBook, side: str, notional_usd: float) -> Fill | None:
    levels = book.asks if side == "long" else book.bids
    quantity = notional_usd / levels[0][0]
    return _depth_fill(book.recv_ts_ms, levels, quantity)


def _exit_fill(book: Hip3ShadowBook, side: str, quantity: float) -> Fill | None:
    return _depth_fill(
        book.recv_ts_ms, book.bids if side == "long" else book.asks, quantity
    )


def _depth_fill(
    timestamp_ms: int, levels: Sequence[tuple[float, float]], quantity: float
) -> Fill | None:
    remaining = quantity
    quote = 0.0
    for price, available in levels:
        filled = min(remaining, available)
        quote += filled * price
        remaining -= filled
        if remaining <= 1e-12:
            return Fill(timestamp_ms, quote / quantity, quantity, quote)
    return None


def _barriers(
    side: str, entry_price: float, config: BrentoilOilShockLifecycleConfig
) -> tuple[float, float]:
    direction = 1.0 if side == "long" else -1.0
    target = entry_price * (1.0 + direction * config.target_bps / 10_000.0)
    stop = entry_price * (1.0 - direction * config.stop_bps / 10_000.0)
    return target, stop


def _barrier_reason(side: str, mark: float, target: float, stop: float) -> str | None:
    if (side == "long" and mark >= target) or (side == "short" and mark <= target):
        return "target"
    if (side == "long" and mark <= stop) or (side == "short" and mark >= stop):
        return "stop"
    return None


def _opposite_time(
    decision: Hip3ShadowDecision,
    decisions: Sequence[Hip3ShadowDecision],
    entry_ms: int,
) -> int | None:
    return min(
        (
            value.observed_at_ms
            for value in decisions
            if value.side != decision.side and value.observed_at_ms > entry_ms
        ),
        default=None,
    )


def _mark_path_resolved(
    marks: Sequence[Mark],
    start_ms: int,
    end_ms: int,
    config: BrentoilOilShockLifecycleConfig,
) -> bool:
    timestamps = [
        value.timestamp_ms
        for value in marks
        if start_ms <= value.timestamp_ms <= end_ms
    ]
    quality = hip3_bar_path_quality(
        timestamps,
        start_ms=start_ms,
        end_ms=end_ms + 1,
        maximum_gap_ms=config.maximum_mark_gap_ms,
    )
    return quality["complete"] is True


def _censored(
    decision: Hip3ShadowDecision, reason: str, entry_time_ms: int | None = None
) -> dict[str, object]:
    return {
        "side": decision.side,
        "decision_time_ms": decision.decision_time_ms,
        "reason": reason,
        "entry_time_ms": entry_time_ms,
    }


def _simulation_report(
    resolved: Sequence[Lifecycle],
    censored: Sequence[Mapping[str, object]],
    suppressed: int,
) -> dict[str, object]:
    values = [row.modeled_net_usd_excluding_funding for row in resolved]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    return {
        "resolved_lifecycles": [asdict(row) for row in resolved],
        "censored_lifecycles": [dict(row) for row in censored],
        "summary": {
            "resolved": len(resolved),
            "censored": len(censored),
            "wins": len(wins),
            "losses": len(losses),
            "modeled_net_usd_excluding_funding": sum(values),
            "profit_factor_excluding_funding": (
                sum(wins) / abs(sum(losses)) if losses else None
            ),
            "mean_modeled_net_usd": mean(values) if values else None,
            "net_excluding_largest_winner_usd": (
                sum(values) - max(wins) if wins else None
            ),
        },
        "overlapping_decisions_suppressed": suppressed,
    }


def _report(
    decision_rows: Sequence[Mapping[str, object]],
    candle_rows: Sequence[Mapping[str, object]],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Mark],
    nominal: Mapping[str, object],
    stress: Mapping[str, object],
    config: BrentoilOilShockLifecycleConfig,
) -> dict[str, object]:
    eligible = sum(
        mapping(row.get("decision"), "decision").get("eligible") is True
        for row in decision_rows
    )
    censored = len(cast(list[object], nominal["censored_lifecycles"]))
    resolved = len(cast(list[object], nominal["resolved_lifecycles"]))
    return {
        "schema_version": "brentoil_oil_shock_lifecycle_v1",
        "symbol": BRENTOIL_OIL_SHOCK_SYMBOL,
        "provider_id": BRENTOIL_OIL_SHOCK_PROVIDER_ID,
        "profile_id": BRENTOIL_OIL_SHOCK_PROFILE_ID,
        "execution_authority": "none",
        "report_only": True,
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "contract": _contract(config),
        "source": _source_counts(
            decision_rows, candle_rows, books, marks, nominal, eligible
        ),
        "nominal": dict(nominal),
        "stress": dict(stress),
        "technical_assessment": {
            "status": _technical_status(eligible, censored),
            "all_observed_paths_resolved": eligible > 0
            and censored == 0
            and resolved > 0,
            "live_change_supported": False,
        },
        "limitations": [
            "modeled net excludes funding and is not realized PnL",
            "mark-triggered exits use the next complete recorded REST depth",
            "small prospective samples cannot establish strategy edge",
            "this report grants no execution, sizing, routing, or promotion authority",
        ],
    }


def _source_counts(
    decisions: Sequence[Mapping[str, object]],
    candles: Sequence[Mapping[str, object]],
    books: Sequence[Hip3ShadowBook],
    marks: Sequence[Mark],
    nominal: Mapping[str, object],
    eligible: int,
) -> dict[str, object]:
    return {
        "observed_decisions": len(decisions),
        "eligible_decisions": eligible,
        "candle_rows": len(candles),
        "book_rows": len(books),
        "exact_mark_rows": len(marks),
        "overlapping_decisions_suppressed": nominal["overlapping_decisions_suppressed"],
    }


def _technical_status(eligible: int, censored: int) -> str:
    if eligible == 0:
        return "WAITING_ELIGIBLE_ONSET"
    if censored:
        return "TECHNICALLY_UNRESOLVED"
    return "PROSPECTIVE_SAMPLE_RESOLVED"


def _contract(config: BrentoilOilShockLifecycleConfig) -> dict[str, object]:
    return {
        "signal_source": BRENTOIL_SIGNAL_SOURCE,
        "entry": "first_complete_rest_depth_after_signal_publication",
        "exit_priority": "target_or_stop_or_opposite_signal_or_60m_max_hold",
        "target_bps": config.target_bps,
        "stop_bps": config.stop_bps,
        "maximum_hold_ms": config.maximum_hold_ms,
        "notional_usd": config.notional_usd,
        "fee_bps_per_side": config.fee_bps_per_side,
        "nominal_residual_bps_per_side": config.nominal_residual_bps_per_side,
        "stress_residual_bps_per_side": config.stress_residual_bps_per_side,
        "maximum_book_lateness_ms": config.maximum_book_lateness_ms,
        "maximum_mark_gap_ms": config.maximum_mark_gap_ms,
        "funding_included": False,
        "friction_source": config.friction_source,
    }
