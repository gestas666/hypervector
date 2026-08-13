"""Report-only readiness and cadence evidence for one disarmed cohort run."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

from hypervector.research.cohort_observer_audit_values import (
    Evaluation,
    Pair,
    Record,
    _cycle_evaluations,
    _evaluation_identities,
    _evaluations,
    _event_rows,
    _expected_pairs,
    _initial_candle_symbols,
    _integer,
    _is_disarmed,
    _is_future,
    _mapping,
    _number,
    _numeric_summary,
    _object_list,
    _pair,
    _pairs,
    _payload,
    _strategy_name,
    _symbols,
    _text,
    _text_list,
    _timestamp,
)
from hypervector.research.cohort_signal_outcomes import (
    build_provider_forward_diagnostics,
)
from hypervector.research.cohort_canonical_regime_telemetry import (
    build_canonical_regime_telemetry_summary,
)
from hypervector.research.cohort_observer_regime_forward_accuracy import (
    build_selected_observer_regime_forward_accuracy,
)
from hypervector.research.cohort_strategy_scorecard import (
    build_strategy_scorecard,
)

_STRATEGY_NAME = "multi_asset_bidirectional_cohort"
_EXECUTION_EVENTS = frozenset(
    {
        "order_intent",
        "cancel_intent",
        "order_acknowledgement",
        "fill",
        "stop_order",
        "target_order",
        "position",
        "fee",
        "funding",
        "liquidation_price",
        "close",
        "reconciliation",
        "cohort_snapshot",
    }
)


def audit_cohort_observer_run(
    records: Sequence[Record],
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Build a causal setup-process audit without inferring trading outcomes."""
    validated = _validated_records(records)
    selected, identity = _select_observer_run(validated, run_id)
    symbols = _symbols(identity)
    expected = _expected_pairs(identity)
    cycles = _event_rows(selected, "intent_routing")
    evaluations = _evaluations(cycles)
    signals = _signal_summary(selected, cycles, evaluations)
    signal_outcomes = build_provider_forward_diagnostics(selected)
    readiness = _readiness_summary(evaluations, expected)
    regime_accuracy = build_selected_observer_regime_forward_accuracy(
        selected,
        identity=identity,
    )
    technical = _technical_summary(
        selected,
        cycles,
        evaluations,
        symbols,
        expected,
        signals,
        signal_outcomes,
    )
    return {
        "schema_version": 3,
        "mode": "multi_asset_bidirectional_observer_audit",
        "observer_contract": _observer_contract(),
        "run": _run_summary(selected, identity, symbols),
        "runtime": _runtime_summary(selected, cycles, evaluations),
        "technical": technical,
        "signals": signals,
        "readiness": readiness,
        "canonical_regime_telemetry": build_canonical_regime_telemetry_summary(
            selected
        ),
        "signal_outcomes": signal_outcomes,
        "regime_forward_accuracy": regime_accuracy,
        "strategy_scorecard": build_strategy_scorecard(
            expected,
            _mapping(readiness.get("by_provider_symbol"), "readiness providers"),
            signal_outcomes,
        ),
        "learning": _learning_summary(),
        "limitations": _limitations(),
    }


def _validated_records(records: Sequence[Record]) -> tuple[Record, ...]:
    if not records:
        raise ValueError("cohort observer audit requires at least one record")
    output = tuple(records)
    for expected, row in enumerate(output, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"cohort ledger row {expected} must be an object")
        if row.get("sequence") != expected:
            raise ValueError(f"cohort ledger sequence must be contiguous at {expected}")
        _mapping(row.get("payload"), "ledger payload")
    return output


def _select_observer_run(
    records: Sequence[Record],
    requested: str | None,
) -> tuple[tuple[Record, ...], Record]:
    identities = [
        row
        for row in _event_rows(records, "configuration_identity")
        if _is_disarmed(row) and _strategy_name(row) == _STRATEGY_NAME
    ]
    chosen = requested or (
        _text(identities[-1].get("run_id"), "run_id") if identities else None
    )
    if chosen is None:
        raise ValueError("cohort observer audit found no disarmed observer run")
    selected = tuple(row for row in records if row.get("run_id") == chosen)
    if not selected or not all(_is_disarmed(row) for row in selected):
        raise ValueError(f"run {chosen} is not a disarmed observer run")
    run_identities = _event_rows(selected, "configuration_identity")
    if len(run_identities) != 1 or _strategy_name(run_identities[0]) != _STRATEGY_NAME:
        raise ValueError(f"run {chosen} has invalid observer configuration identity")
    execution_events = sorted(
        str(row.get("event_type"))
        for row in selected
        if row.get("event_type") in _EXECUTION_EVENTS
    )
    if execution_events:
        raise ValueError(f"observer run contains execution events: {execution_events}")
    return selected, run_identities[0]


def _observer_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "orders_observed": False,
        "fills_observed": False,
        "profitability_measured": False,
        "performance_gate": False,
        "runtime_strategy_changed": False,
    }


def _run_summary(
    records: Sequence[Record],
    identity: Record,
    symbols: tuple[str, ...],
) -> dict[str, object]:
    return {
        "run_id": identity.get("run_id"),
        "profile_id": identity.get("profile_id"),
        "profile_fingerprint": identity.get("profile_fingerprint"),
        "run_fingerprint": identity.get("run_fingerprint"),
        "symbols": list(symbols),
        "row_count": len(records),
        "first_observed_at_utc": records[0].get("observed_at_utc"),
        "last_observed_at_utc": records[-1].get("observed_at_utc"),
        "duration_seconds": (
            _timestamp(records[-1]) - _timestamp(records[0])
        ).total_seconds(),
    }


def _runtime_summary(
    records: Sequence[Record],
    cycles: Sequence[Record],
    evaluations: Sequence[Evaluation],
) -> dict[str, object]:
    heartbeats = _event_rows(records, "heartbeat")
    degraded = [
        _payload(row) for row in heartbeats if _payload(row).get("status") == "degraded"
    ]
    heartbeat_times = [_timestamp(row) for row in heartbeats]
    intervals = [
        (right - left).total_seconds()
        for left, right in zip(heartbeat_times, heartbeat_times[1:])
    ]
    evaluation_cycles = sum(
        bool(_object_list(_payload(row), "evaluations")) for row in cycles
    )
    return {
        "poll_cycles": len(heartbeats),
        "successful_poll_cycles": len(heartbeats) - len(degraded),
        "degraded_poll_cycles": len(degraded),
        "degraded_sources": dict(
            sorted(
                Counter(
                    _text(value.get("source"), "degraded source") for value in degraded
                ).items()
            )
        ),
        "degraded_reasons": dict(
            sorted(
                Counter(
                    _text(value.get("reason"), "degraded reason") for value in degraded
                ).items()
            )
        ),
        "routing_cycles": len(cycles),
        "evaluation_cycles": evaluation_cycles,
        "quiet_routing_cycles": len(cycles) - evaluation_cycles,
        "evaluation_count": len(evaluations),
        "heartbeat_interval_seconds": _numeric_summary(intervals),
    }


def _technical_summary(
    records: Sequence[Record],
    cycles: Sequence[Record],
    evaluations: Sequence[Evaluation],
    symbols: tuple[str, ...],
    expected: frozenset[Pair],
    signals: Mapping[str, object],
    signal_outcomes: Mapping[str, object],
) -> dict[str, object]:
    initial_pairs = _pairs(_cycle_evaluations(cycles[0])) if cycles else []
    observed_pairs = _pairs([value for _, value in evaluations])
    duplicate_count = len(_evaluation_identities(evaluations)) - len(
        set(_evaluation_identities(evaluations))
    )
    future_count = sum(_is_future(arrival, value) for arrival, value in evaluations)
    initial_candles = _initial_candle_symbols(records)
    gaps = _technical_gaps(
        initial_pairs,
        observed_pairs,
        expected,
        initial_candles,
        symbols,
        duplicate_count,
        future_count,
        _integer(signals.get("routed_actions"), "routed actions"),
    )
    outcome_coverage = _mapping(
        signal_outcomes.get("coverage"), "signal outcome coverage"
    )
    if _integer(outcome_coverage.get("direction_conflicts"), "direction conflicts"):
        gaps.append("provider_direction_telemetry_conflict")
        gaps.sort()
    return {
        "complete": not gaps,
        "technical_gaps": gaps,
        "expected_provider_symbols": len(expected),
        "initial_provider_symbols": len(set(initial_pairs)),
        "observed_provider_symbols": len(set(observed_pairs)),
        "missing_observed_provider_symbols": [
            f"{provider}|{symbol}"
            for provider, symbol in sorted(expected.difference(observed_pairs))
        ],
        "initial_candle_symbols": sorted(initial_candles),
        "duplicate_evaluations": duplicate_count,
        "future_decisions": future_count,
        "decision_timing_seconds": _decision_timing(cycles),
    }


def _technical_gaps(
    initial_pairs: Sequence[Pair],
    observed_pairs: Sequence[Pair],
    expected: frozenset[Pair],
    candle_symbols: frozenset[str],
    symbols: tuple[str, ...],
    duplicates: int,
    future: int,
    actions: int,
) -> list[str]:
    gaps: list[str] = []
    if duplicates:
        gaps.append("duplicate_evaluation_identity")
    if future:
        gaps.append("future_decision_timestamp")
    if candle_symbols != frozenset(symbols):
        gaps.append("initial_candle_coverage_incomplete")
    if set(initial_pairs) != expected or len(initial_pairs) != len(expected):
        gaps.append("initial_provider_coverage_incomplete")
    if not set(observed_pairs).issubset(expected):
        gaps.append("unknown_provider_symbol")
    if actions:
        gaps.append("observer_routed_action_present")
    return sorted(gaps)


def _signal_summary(
    records: Sequence[Record],
    cycles: Sequence[Record],
    evaluations: Sequence[Evaluation],
) -> dict[str, object]:
    actions = [
        item for row in cycles for item in _object_list(_payload(row), "actions")
    ]
    withheld = [
        item for row in cycles for item in _object_list(_payload(row), "withheld")
    ]
    reasons = Counter(_text(item.get("reason"), "withheld reason") for item in withheld)
    return {
        "strategy_intents": len(_event_rows(records, "strategy_intent")),
        "eligible_evaluations": sum(
            value.get("eligible") is True for _, value in evaluations
        ),
        "routed_actions": len(actions),
        "withheld_intents": len(withheld),
        "withheld_reasons": dict(sorted(reasons.items())),
    }


def _readiness_summary(
    evaluations: Sequence[Evaluation],
    expected: frozenset[Pair],
) -> dict[str, object]:
    grouped: dict[Pair, list[Record]] = defaultdict(list)
    for _, evaluation in evaluations:
        grouped[_pair(evaluation)].append(evaluation)
    summaries = {
        f"{provider}|{symbol}": _provider_summary(values)
        for (provider, symbol), values in sorted(grouped.items())
    }
    return {
        "evaluations": len(evaluations),
        "expected_provider_symbols": len(expected),
        "observed_provider_symbols": len(grouped),
        "by_provider_symbol": summaries,
    }


def _provider_summary(evaluations: Sequence[Record]) -> dict[str, object]:
    fractions = [_readiness_fraction(value) for value in evaluations]
    signatures = [_readiness_signature(value) for value in evaluations]
    deltas = [right - left for left, right in zip(fractions, fractions[1:])]
    latest = evaluations[-1]
    latest_readiness = _mapping(latest.get("readiness"), "latest readiness")
    blockers = Counter(
        blocker
        for value in evaluations
        for blocker in _text_list(
            _mapping(value.get("readiness"), "readiness").get("blockers"), "blockers"
        )
    )
    reasons = Counter(
        _text(value.get("reason"), "evaluation reason") for value in evaluations
    )
    return {
        "count": len(evaluations),
        "eligible": sum(value.get("eligible") is True for value in evaluations),
        "first_fraction": fractions[0],
        "latest_fraction": fractions[-1],
        "minimum_fraction": min(fractions),
        "maximum_fraction": max(fractions),
        "mean_fraction": sum(fractions) / len(fractions),
        "progressions": sum(delta > 0.0 for delta in deltas),
        "regressions": sum(delta < 0.0 for delta in deltas),
        "unchanged": sum(delta == 0.0 for delta in deltas),
        "state_transitions": sum(
            left != right for left, right in zip(signatures, signatures[1:])
        ),
        "latest_side": latest_readiness.get("side"),
        "latest_reason": latest.get("reason"),
        "latest_blockers": _text_list(
            latest_readiness.get("blockers"), "latest blockers"
        ),
        "latest_indicators": _text_list(
            latest_readiness.get("indicators"), "latest indicators"
        ),
        "blockers": dict(sorted(blockers.items())),
        "reasons": dict(sorted(reasons.items())),
    }


def _readiness_signature(evaluation: Record) -> tuple[object, ...]:
    readiness = _mapping(evaluation.get("readiness"), "readiness")
    return (
        _integer(readiness.get("conditions_met"), "conditions met"),
        _integer(readiness.get("conditions_required"), "conditions required"),
        evaluation.get("eligible"),
        readiness.get("side"),
        evaluation.get("reason"),
        tuple(_text_list(readiness.get("blockers"), "readiness blockers")),
    )


def _readiness_fraction(evaluation: Record) -> float:
    readiness = _mapping(evaluation.get("readiness"), "readiness")
    value = _number(readiness.get("readiness_fraction"), "readiness fraction")
    if not 0.0 <= value <= 1.0:
        raise ValueError("readiness fraction must be within [0, 1]")
    return value


def _arrival_lags(evaluations: Sequence[Evaluation]) -> dict[str, object]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for arrival, evaluation in evaluations:
        provider = _text(evaluation.get("strategy_id"), "evaluation strategy")
        decision_ms = _integer(evaluation.get("decision_time_ms"), "decision time")
        grouped[provider].append(
            (_timestamp(arrival).timestamp() * 1_000 - decision_ms) / 1_000
        )
    return {
        provider: _numeric_summary(values)
        for provider, values in sorted(grouped.items())
    }


def _decision_timing(cycles: Sequence[Record]) -> dict[str, object]:
    """Separate startup seed age from post-start decision arrival lag."""
    startup = _evaluations(cycles[:1])
    steady_state = _evaluations(cycles[1:])
    return {
        "startup_seed_age_by_provider": _arrival_lags(startup),
        "steady_state_arrival_lag_by_provider": _arrival_lags(steady_state),
    }


def _learning_summary() -> dict[str, object]:
    return {
        "evidence_state": "setup_and_signal_paths_only_no_execution_outcomes",
        "signal_path_descriptives_identifiable": True,
        "strategy_edge_identifiable": False,
        "profitability_identifiable": False,
        "execution_quality_identifiable": False,
        "valid_uses": [
            "technical_parity",
            "signal_cadence",
            "setup_progression",
            "blocker_attribution",
        ],
    }


def _limitations() -> list[str]:
    return [
        "No orders, fills, fees, funding, slippage, markout, or realized PnL were observed.",
        "Forward candle paths are counterfactual signal diagnostics, not execution outcomes.",
        "Readiness is prerequisite completion, not win probability or expected return.",
        "This audit cannot promote, filter, size, pause, or retune a strategy.",
    ]
