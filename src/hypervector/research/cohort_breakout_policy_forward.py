"""Report-only all-asset breakout lifecycle evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research import cohort_breakout_provider_contention as contention
from hypervector.research.cohort_breakout_execution_reconciliation import (
    reconcile_breakout_execution,
)
from hypervector.research.cohort_breakout_policy_models import (
    BreakoutPolicyForwardSpec,
    breakout_report_contract,
    breakout_report_limitations,
)
from hypervector.research.cohort_forward_paths import (
    MINUTE_MS,
    Candle,
    build_candle_index,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

_CANONICAL_STRATEGY = "range_onset_bidirectional_v1"
_SUPPORT_THRESHOLD = 0.5


def build_breakout_policy_forward_report(
    records: Sequence[Mapping[str, object]],
    *,
    spec: BreakoutPolicyForwardSpec,
) -> dict[str, object]:
    """Build exact-policy report-only lifecycles from recorded evaluations."""
    run_records = tuple(
        row for row in records if row.get("run_id") == spec.source_run_id
    )
    candidates, excluded, conflicts = evaluation_candidates(run_records)
    relevant = tuple(
        value
        for value in candidates
        if value.source_run_id == spec.source_run_id
        and value.symbol in spec.symbols
        and value.decision_time_ms >= spec.cutoff_time_ms
    )
    entries = tuple(
        value
        for value in relevant
        if value.strategy_id == spec.source_strategy_id and value.eligible
    )
    candles = build_candle_index(run_records)
    lifecycles, counts = _resolve_entries(entries, relevant, candles, spec)
    lifecycles, actual_execution = reconcile_breakout_execution(
        run_records, lifecycles, spec=spec
    )
    summary = _summary(entries, lifecycles, counts, excluded, conflicts)
    summary["actual_execution"] = actual_execution
    summary.update(contention.contention_summary(relevant, spec))
    return {
        "schema_version": 1,
        "mode": "cohort_breakout_policy_forward_report",
        "contract": breakout_report_contract(spec),
        "summary": summary,
        "lifecycles": lifecycles,
        "limitations": breakout_report_limitations(),
    }


def _resolve_entries(
    entries: Sequence[SignalCandidate],
    contexts: Sequence[SignalCandidate],
    candles: Mapping[str, Mapping[int, Candle]],
    spec: BreakoutPolicyForwardSpec,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    lifecycles: list[dict[str, object]] = []
    counts = {"same_side_occupied": 0, "opposite_close_signals": 0}
    ordered = sorted(entries, key=lambda value: (value.decision_time_ms, value.symbol))
    next_available = {symbol: -1 for symbol in spec.symbols}
    unresolved_symbols: set[str] = set()
    for entry in ordered:
        if (
            entry.symbol in unresolved_symbols
            or entry.decision_time_ms <= next_available[entry.symbol]
        ):
            continue
        same_symbol = tuple(value for value in ordered if value.symbol == entry.symbol)
        lifecycle, consumed, occupied, opposite = _resolve_lifecycle(
            entry,
            same_symbol,
            contexts,
            candles.get(entry.symbol, {}),
            spec,
        )
        lifecycles.append(lifecycle)
        if lifecycle["status"] != "resolved":
            unresolved_symbols.add(entry.symbol)
        next_available[entry.symbol] = consumed
        counts["same_side_occupied"] += occupied
        counts["opposite_close_signals"] += opposite
    return lifecycles, counts


def _resolve_lifecycle(
    entry: SignalCandidate,
    entries: Sequence[SignalCandidate],
    contexts: Sequence[SignalCandidate],
    candles: Mapping[int, Candle],
    spec: BreakoutPolicyForwardSpec,
) -> tuple[dict[str, object], int, int, int]:
    base, stop_price, hard_boundary = _lifecycle_values(entry, spec)
    favorable = adverse = 0.0
    occupied = 0
    soft_decision: dict[str, object] | None = None
    for boundary in range(entry.decision_time_ms, hard_boundary + 1, MINUTE_MS):
        if boundary > entry.decision_time_ms:
            result, soft_decision, occupied_delta, opposite = _boundary_resolution(
                entry,
                boundary,
                entries,
                contexts,
                candles,
                spec,
                base,
                soft_decision,
                favorable,
                adverse,
            )
            occupied += occupied_delta
            if result is not None:
                return result, boundary, occupied, opposite
        candle = candles.get(boundary)
        if candle is None:
            return (
                _unresolved(base, boundary, candles, favorable, adverse, spec),
                hard_boundary,
                occupied,
                0,
            )
        result, favorable, adverse = _candle_stop_resolution(
            entry,
            candle,
            boundary,
            stop_price,
            base,
            spec,
            soft_decision,
            favorable,
            adverse,
        )
        if result is not None:
            return result, boundary, occupied, 0
    raise RuntimeError("breakout lifecycle exceeded its validated hard boundary")


def _lifecycle_values(
    entry: SignalCandidate,
    spec: BreakoutPolicyForwardSpec,
) -> tuple[dict[str, object], float, int]:
    return (
        _base(entry, spec),
        _stop_price(entry, spec.stop_bps),
        entry.decision_time_ms + spec.hard_hold_minutes * MINUTE_MS,
    )


def _candle_stop_resolution(
    entry: SignalCandidate,
    candle: Candle,
    boundary: int,
    stop_price: float,
    base: Mapping[str, object],
    spec: BreakoutPolicyForwardSpec,
    soft_decision: Mapping[str, object] | None,
    favorable: float,
    adverse: float,
) -> tuple[dict[str, object] | None, float, float]:
    favorable, adverse = _excursions(entry, candle, favorable, adverse)
    if not _stop_touched(entry.side, candle, stop_price):
        return None, favorable, adverse
    result = _resolved(
        base,
        boundary + MINUTE_MS,
        stop_price,
        "protective_stop",
        favorable,
        adverse,
        spec,
    )
    result["soft_decision"] = soft_decision
    result["terminal_structure_alignment_score"] = None
    return result, favorable, adverse


def _boundary_resolution(
    entry: SignalCandidate,
    boundary: int,
    entries: Sequence[SignalCandidate],
    contexts: Sequence[SignalCandidate],
    candles: Mapping[int, Candle],
    spec: BreakoutPolicyForwardSpec,
    base: Mapping[str, object],
    soft_decision: dict[str, object] | None,
    favorable: float,
    adverse: float,
) -> tuple[dict[str, object] | None, dict[str, object] | None, int, int]:
    timer = _timer_decision(entry, boundary, contexts, spec)
    if timer is not None:
        reason, score, soft_decision = _timer_state(timer, soft_decision)
        if reason is not None:
            price = _boundary_price(entry, boundary, contexts, candles)
            result = _resolved(base, boundary, price, reason, favorable, adverse, spec)
            result["soft_decision"] = soft_decision
            result["terminal_structure_alignment_score"] = score
            return result, soft_decision, 0, 0
    signal = _eligible_at(entries, entry, boundary)
    if signal is None:
        return None, soft_decision, 0, 0
    if signal.side == entry.side:
        return None, soft_decision, 1, 0
    result = _resolved(
        base,
        boundary,
        signal.reference_price,
        "opposite_strategy_intent",
        favorable,
        adverse,
        spec,
    )
    result["soft_decision"] = soft_decision
    result["terminal_structure_alignment_score"] = None
    return result, soft_decision, 0, 1


def _timer_decision(
    entry: SignalCandidate,
    boundary: int,
    contexts: Sequence[SignalCandidate],
    spec: BreakoutPolicyForwardSpec,
) -> tuple[str | None, float | None, int] | None:
    elapsed = boundary - entry.decision_time_ms
    soft_ms = spec.soft_hold_minutes * MINUTE_MS
    if elapsed < soft_ms:
        return None
    score = _structure_score(entry, boundary, contexts)
    if elapsed >= spec.hard_hold_minutes * MINUTE_MS:
        return "hard_maximum_hold_seconds", score, boundary
    reason = (
        None
        if score is not None and score >= _SUPPORT_THRESHOLD
        else "maximum_hold_seconds"
    )
    return reason, score, boundary


def _timer_state(
    timer: tuple[str | None, float | None, int],
    soft_decision: dict[str, object] | None,
) -> tuple[str | None, float | None, dict[str, object]]:
    reason, score, boundary = timer
    if soft_decision is None:
        soft_decision = {
            "decision_time_ms": boundary,
            "outcome": "extend" if reason is None else "exit",
            "structure_alignment_score": score,
            "structure_alignment_threshold": _SUPPORT_THRESHOLD,
        }
    return reason, score, soft_decision


def _structure_score(
    entry: SignalCandidate,
    boundary: int,
    candidates: Sequence[SignalCandidate],
) -> float | None:
    provider = _latest_candidate(
        candidates, entry.source_run_id, entry.symbol, entry.strategy_id, boundary
    )
    canonical = _latest_candidate(
        candidates, entry.source_run_id, entry.symbol, _CANONICAL_STRATEGY, boundary
    )
    assessment = build_regime_assessment(
        entry.side or "",
        {
            "signal_provider": _regime_context(provider),
            "canonical_regime": _regime_context(canonical),
        },
    )
    value = assessment["structure_support_score"]
    return float(value) if isinstance(value, (int, float)) else None


def _regime_context(candidate: SignalCandidate | None) -> dict[str, object]:
    if candidate is None:
        return {"status": "unavailable"}
    metrics = dict(candidate.metrics)
    return {
        "status": "observed",
        "side": candidate.side,
        "primary_regime": metrics.get("primary_regime"),
        "state_1m": metrics.get("state_1m"),
        "state_5m": metrics.get("state_5m"),
        "context_15m": metrics.get("context_15m"),
        "readiness": {"metrics": metrics},
    }


def _latest_candidate(
    candidates: Sequence[SignalCandidate],
    run_id: str | None,
    symbol: str,
    strategy_id: str,
    boundary: int,
) -> SignalCandidate | None:
    eligible = (
        value
        for value in candidates
        if value.source_run_id == run_id
        and value.symbol == symbol
        and value.strategy_id == strategy_id
        and value.decision_time_ms <= boundary
    )
    return max(eligible, key=lambda value: value.decision_time_ms, default=None)


def _eligible_at(
    entries: Sequence[SignalCandidate],
    opened: SignalCandidate,
    boundary: int,
) -> SignalCandidate | None:
    matches = [
        value
        for value in entries
        if value is not opened and value.decision_time_ms == boundary
    ]
    if len(matches) > 1:
        raise ValueError("multiple breakout onsets share one symbol decision boundary")
    return matches[0] if matches else None


def _boundary_price(
    entry: SignalCandidate,
    boundary: int,
    contexts: Sequence[SignalCandidate],
    candles: Mapping[int, Candle],
) -> float:
    provider = _latest_candidate(
        contexts, entry.source_run_id, entry.symbol, entry.strategy_id, boundary
    )
    if provider is not None and provider.decision_time_ms == boundary:
        return provider.reference_price
    prior = candles.get(boundary - MINUTE_MS)
    if prior is None:
        raise ValueError("timer exit lacks a causal boundary price")
    return prior.close


def _stop_price(entry: SignalCandidate, stop_bps: float) -> float:
    fraction = stop_bps / 10_000.0
    return entry.reference_price * (
        1.0 - fraction if entry.side == "long" else 1.0 + fraction
    )


def _stop_touched(side: str | None, candle: Candle, stop_price: float) -> bool:
    if side == "long":
        return candle.low <= stop_price
    if side == "short":
        return candle.high >= stop_price
    raise ValueError("eligible breakout lifecycle requires long or short")


def _excursions(
    entry: SignalCandidate,
    candle: Candle,
    favorable: float,
    adverse: float,
) -> tuple[float, float]:
    if entry.side == "long":
        latest_favorable = (candle.high / entry.reference_price - 1.0) * 10_000.0
        latest_adverse = (1.0 - candle.low / entry.reference_price) * 10_000.0
    else:
        latest_favorable = (1.0 - candle.low / entry.reference_price) * 10_000.0
        latest_adverse = (candle.high / entry.reference_price - 1.0) * 10_000.0
    return max(favorable, latest_favorable, 0.0), max(adverse, latest_adverse, 0.0)


def _base(entry: SignalCandidate, spec: BreakoutPolicyForwardSpec) -> dict[str, object]:
    return {
        "strategy_id": entry.strategy_id,
        "symbol": entry.symbol,
        "side": entry.side,
        "signal_time_ms": entry.decision_time_ms,
        "causal_available_time_ms": entry.available_time_ms,
        "entry_time_ms": entry.decision_time_ms,
        "entry_price": entry.reference_price,
        "entry_attribution": _entry_attribution(entry),
        "stop_price": _stop_price(entry, spec.stop_bps),
        "soft_deadline_time_ms": entry.decision_time_ms
        + spec.soft_hold_minutes * MINUTE_MS,
        "hard_deadline_time_ms": entry.decision_time_ms
        + spec.hard_hold_minutes * MINUTE_MS,
    }


def _entry_attribution(entry: SignalCandidate) -> dict[str, object]:
    fields = (
        "breakout_side",
        "breakout_side_relation",
        "confidence",
        "entry_feature_status",
    )
    return {name: entry.metrics.get(name) for name in fields}


def _resolved(
    base: Mapping[str, object],
    exit_time_ms: int,
    exit_price: float,
    reason: str,
    favorable: float,
    adverse: float,
    spec: BreakoutPolicyForwardSpec,
) -> dict[str, object]:
    side = str(base["side"])
    entry_price = float(base["entry_price"])
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price / entry_price - 1.0) * 10_000.0
    net = gross - spec.modeled_round_trip_friction_bps
    symbol = str(base["symbol"])
    return dict(base) | {
        "status": "resolved",
        "exit_time_ms": exit_time_ms,
        "exit_price": exit_price,
        "exit_reason": reason,
        "gross_return_bps": gross,
        "modeled_round_trip_friction_bps": spec.modeled_round_trip_friction_bps,
        "estimated_net_return_bps": net,
        "estimated_net_pnl_usd": spec.notional_usd_by_symbol[symbol] * net / 10_000.0,
        "mfe_bps": favorable,
        "mae_bps": adverse,
    }


def _unresolved(
    base: Mapping[str, object],
    missing_boundary: int,
    candles: Mapping[int, Candle],
    favorable: float,
    adverse: float,
    spec: BreakoutPolicyForwardSpec,
) -> dict[str, object]:
    later_exists = bool(candles) and max(candles) > missing_boundary
    output = dict(base) | {
        "status": "missing_data" if later_exists else "pending",
        "missing_or_next_boundary_time_ms": missing_boundary,
        "mfe_bps": favorable,
        "mae_bps": adverse,
    }
    prior = candles.get(missing_boundary - MINUTE_MS)
    if prior is not None:
        direction = 1.0 if base["side"] == "long" else -1.0
        gross = direction * (prior.close / float(base["entry_price"]) - 1.0) * 10_000.0
        output["current_gross_return_bps"] = gross
        output["current_estimated_net_return_bps"] = (
            gross - spec.modeled_round_trip_friction_bps
        )
    return output


def _summary(
    entries: Sequence[SignalCandidate],
    lifecycles: Sequence[Mapping[str, object]],
    counts: Mapping[str, int],
    excluded: int,
    conflicts: int,
) -> dict[str, object]:
    resolved = [value for value in lifecycles if value.get("status") == "resolved"]
    return {
        "eligible_signals": len(entries),
        "lifecycles": len(lifecycles),
        "resolved": len(resolved),
        "pending": sum(value.get("status") == "pending" for value in lifecycles),
        "missing_data": sum(
            value.get("status") == "missing_data" for value in lifecycles
        ),
        "same_side_occupied_signals": counts["same_side_occupied"],
        "opposite_close_signals": counts["opposite_close_signals"],
        "preactivation_annotations_excluded": excluded,
        "direction_conflicts": conflicts,
        "estimated_net_return_bps": sum(
            float(value["estimated_net_return_bps"]) for value in resolved
        ),
        "estimated_net_pnl_usd": sum(
            float(value["estimated_net_pnl_usd"]) for value in resolved
        ),
    }
