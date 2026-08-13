"""Route-specific causal regime accuracy for report-only cohort observers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, median

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping_list,
    nonnegative_int,
    number,
    payload,
    positive_int,
    text,
    timestamp,
)
from hypervector.research.cohort_observer_exact_books import (
    select_compatible_report_only_observer_runs,
)
from hypervector.research.cohort_signal_candidates import (
    SignalCandidate,
    evaluation_candidates,
)

Record = Mapping[str, object]
_STATE_FIELDS = ("primary_regime", "state_1m", "state_5m", "context_15m")
_DIRECTIONAL_STATES = {"TREND_UP": 1, "TREND_DOWN": -1}
_RANGE_THRESHOLDS_BPS = (10.0, 25.0, 50.0)
_CANONICAL_STRATEGY = "canonical_regime_telemetry_v1"
_CANONICAL_CONTRACT = {
    "configured_route": False,
    "execution_authority": "none",
    "intents_emitted": False,
}


@dataclass(frozen=True)
class _ResolvedObservation:
    candidate: SignalCandidate
    forward_return_bps: float


def build_observer_regime_forward_accuracy(
    records: Sequence[Record],
    *,
    run_id: str,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
) -> dict[str, object]:
    """Score exact later route observations without imputing missing states."""
    selected, identities = select_compatible_report_only_observer_runs(records, run_id)
    report = build_selected_observer_regime_forward_accuracy(
        selected, identity=identities[0], horizons_minutes=horizons_minutes
    )
    source = report.get("source")
    if not isinstance(source, dict):
        raise RuntimeError("observer regime report source is invalid")
    source["compatible_run_ids"] = [identity["run_id"] for identity in identities]
    source["compatible_run_count"] = len(identities)
    return report


def build_selected_observer_regime_forward_accuracy(
    records: Sequence[Record],
    *,
    identity: Record,
    horizons_minutes: Sequence[int] = (5, 15, 30, 60),
) -> dict[str, object]:
    """Score a run already fail-closed by the parent observer audit."""
    run_id = _identity_run_id(identity)
    candidates, excluded, conflicts = evaluation_candidates(records)
    canonical = _canonical_candidates(records)
    horizons = _horizons(horizons_minutes)
    grouped = _routes(candidates)
    return {
        "schema_version": 1,
        "mode": "cohort_observer_route_regime_forward_accuracy",
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "performance_gate": False,
        "source": {
            "run_id": run_id,
            "profile_id": identity.get("profile_id"),
            "profile_fingerprint": identity.get("profile_fingerprint"),
            "candidate_observations": len(candidates),
            "pre_activation_excluded": excluded,
            "direction_conflicts": conflicts,
        },
        "horizons": {
            f"{minutes}m": _horizon_report(grouped, minutes) for minutes in horizons
        },
        "canonical_source": _canonical_source(canonical),
        "canonical_horizons": {
            f"{minutes}m": {
                "by_symbol": {
                    symbol: _route_report(values, minutes)
                    for symbol, values in sorted(_canonical_routes(canonical).items())
                }
            }
            for minutes in horizons
        },
        "limitations": [
            "repeated route observations are autocorrelated and descriptive only",
            "episode onsets reduce repetition but are not independent trades",
            "provider routes without complete regime fields remain explicit and unscored",
            "forward reference returns are not fills, fees, funding, or strategy PnL",
            "this diagnostic cannot gate, size, promote, or retune a strategy",
        ],
    }


def _canonical_candidates(records: Sequence[Record]) -> tuple[SignalCandidate, ...]:
    output: list[SignalCandidate] = []
    seen: set[tuple[str, int]] = set()
    for row in event_rows(records, "canonical_regime_evaluations"):
        values = payload(row)
        if values.get("contract") != _CANONICAL_CONTRACT:
            raise ValueError("observer canonical regime contract is invalid")
        available_ms = int(timestamp(row).timestamp() * 1_000)
        for raw in mapping_list(values.get("evaluations"), "canonical evaluations"):
            candidate = _canonical_candidate(raw, available_ms)
            key = (candidate.symbol, candidate.decision_time_ms)
            if key in seen:
                raise ValueError("duplicate observer canonical regime evaluation")
            seen.add(key)
            output.append(candidate)
    return tuple(sorted(output, key=lambda row: (row.symbol, row.decision_time_ms)))


def _canonical_candidate(raw: Record, available_ms: int) -> SignalCandidate:
    decision_ms = nonnegative_int(raw.get("decision_time_ms"), "canonical decision")
    reference = number(raw.get("reference_price"), "canonical reference price")
    valid = (
        raw.get("strategy_id") == _CANONICAL_STRATEGY
        and raw.get("eligible") is False
        and raw.get("side") is None
        and raw.get("decision_action") == "regime_observation"
        and raw.get("reason") == "canonical_regime_observation"
        and raw.get("backend_non_action_reason")
        == "telemetry_only_no_execution_authority"
        and 0.0 < reference
        and decision_ms <= available_ms
    )
    if not valid:
        raise ValueError("observer canonical regime evaluation is invalid")
    metrics = {field: _canonical_state(raw, field) for field in _STATE_FIELDS}
    return SignalCandidate(
        strategy_id=_CANONICAL_STRATEGY,
        symbol=text(raw.get("symbol"), "canonical symbol"),
        decision_time_ms=decision_ms,
        available_time_ms=available_ms,
        reference_price=reference,
        side=None,
        eligible=False,
        blockers=(),
        metrics=metrics,
    )


def _canonical_state(raw: Record, field: str) -> str:
    state = text(raw.get(field), f"canonical {field}")
    if state not in {*_DIRECTIONAL_STATES, "BREAKOUT", "RANGE", "TRANSITION"}:
        raise ValueError(f"canonical {field} is invalid")
    return state


def _canonical_routes(
    candidates: Sequence[SignalCandidate],
) -> dict[str, tuple[SignalCandidate, ...]]:
    grouped: dict[str, list[SignalCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.symbol].append(candidate)
    return {symbol: tuple(values) for symbol, values in grouped.items()}


def _canonical_source(candidates: Sequence[SignalCandidate]) -> dict[str, object]:
    return {
        "strategy_id": _CANONICAL_STRATEGY,
        "candidate_observations": len(candidates),
        "symbols": len({value.symbol for value in candidates}),
        "configured_route": False,
        "execution_authority": "none",
    }


def _identity_run_id(identity: Record) -> str:
    value = identity.get("run_id")
    if not isinstance(value, str) or not value:
        raise ValueError("observer regime identity requires a run id")
    return value


def _horizon_report(
    routes: Mapping[str, Sequence[SignalCandidate]], minutes: int
) -> dict[str, object]:
    return {
        "horizon_minutes": minutes,
        "by_provider_symbol": {
            route: _route_report(candidates, minutes)
            for route, candidates in sorted(routes.items())
        },
    }


def _route_report(
    candidates: Sequence[SignalCandidate], minutes: int
) -> dict[str, object]:
    resolved, coverage = _resolve(candidates, minutes)
    onsets = _episode_onsets(candidates)
    return {
        "coverage": {
            **coverage,
            "complete_state_observations": sum(
                _complete_states(candidate) for candidate in candidates
            ),
        },
        "state_fields": {
            field: _field_report(resolved, onsets, field) for field in _STATE_FIELDS
        },
    }


def _resolve(
    candidates: Sequence[SignalCandidate], minutes: int
) -> tuple[tuple[_ResolvedObservation, ...], dict[str, int]]:
    lookup = {candidate.decision_time_ms: candidate for candidate in candidates}
    maximum = max(lookup) if lookup else -1
    delta = minutes * 60_000
    resolved: list[_ResolvedObservation] = []
    tail = missing = 0
    for candidate in candidates:
        target = candidate.decision_time_ms + delta
        future = lookup.get(target)
        if future is None:
            tail += target > maximum
            missing += target <= maximum
            continue
        value = (future.reference_price / candidate.reference_price - 1.0) * 10_000.0
        resolved.append(_ResolvedObservation(candidate, value))
    return tuple(resolved), {
        "candidate_observations": len(candidates),
        "resolved_future_prices": len(resolved),
        "unresolved_tail": tail,
        "missing_exact_future": missing,
    }


def _episode_onsets(
    candidates: Sequence[SignalCandidate],
) -> frozenset[tuple[int, str]]:
    prior: dict[str, str] = {}
    output: set[tuple[int, str]] = set()
    for candidate in candidates:
        for field in _STATE_FIELDS:
            state = _state(candidate, field)
            if state is None:
                continue
            if field in prior and prior[field] != state:
                output.add((candidate.decision_time_ms, field))
            prior[field] = state
    return frozenset(output)


def _field_report(
    resolved: Sequence[_ResolvedObservation],
    onsets: frozenset[tuple[int, str]],
    field: str,
) -> dict[str, object]:
    repeated = [row for row in resolved if _state(row.candidate, field) is not None]
    episodes = [
        row for row in repeated if (row.candidate.decision_time_ms, field) in onsets
    ]
    return {
        "repeated": _group_metrics(repeated, field),
        "episode_onsets": _group_metrics(episodes, field),
    }


def _group_metrics(
    rows: Sequence[_ResolvedObservation], field: str
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        state = _state(row.candidate, field)
        if state is not None:
            grouped[state].append(row.forward_return_bps)
    return {state: _metrics(state, values) for state, values in sorted(grouped.items())}


def _metrics(state: str, values: Sequence[float]) -> dict[str, object]:
    absolute = [abs(value) for value in values]
    return {
        "observations": len(values),
        "mean_forward_return_bps": mean(values),
        "median_forward_return_bps": median(values),
        "mean_absolute_return_bps": mean(absolute),
        "median_absolute_return_bps": median(absolute),
        "directional_accuracy_pct": _directional_accuracy(state, values),
        "quiet_rate_by_threshold_pct": {
            f"lt_{threshold:g}bps": 100.0
            * sum(value < threshold for value in absolute)
            / len(absolute)
            for threshold in _RANGE_THRESHOLDS_BPS
        },
    }


def _directional_accuracy(state: str, values: Sequence[float]) -> float | None:
    direction = _DIRECTIONAL_STATES.get(state)
    if direction is None:
        return None
    correct = sum(value * direction > 0.0 for value in values)
    return 100.0 * correct / len(values)


def _routes(
    candidates: Sequence[SignalCandidate],
) -> dict[str, tuple[SignalCandidate, ...]]:
    grouped: dict[str, list[SignalCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[f"{candidate.strategy_id}|{candidate.symbol}"].append(candidate)
    return {
        route: tuple(sorted(values, key=lambda item: item.decision_time_ms))
        for route, values in grouped.items()
    }


def _complete_states(candidate: SignalCandidate) -> bool:
    return all(_state(candidate, field) is not None for field in _STATE_FIELDS)


def _state(candidate: SignalCandidate, field: str) -> str | None:
    value = candidate.metrics.get(field)
    return value if isinstance(value, str) else None


def _horizons(values: Sequence[int]) -> tuple[int, ...]:
    horizons = tuple(positive_int(value, "regime horizon") for value in values)
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("regime horizons must be unique and non-empty")
    return horizons
