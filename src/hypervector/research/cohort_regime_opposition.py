"""Report-only persistence evidence for regime opposition during a lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    nonnegative_int,
    number,
)
from hypervector.research.cohort_regime_assessment import build_regime_assessment
from hypervector.research.cohort_signal_candidates import (
    is_technical_unavailability,
)

Record = Mapping[str, object]
_DECISION_INTERVAL_MS = 60_000
_OPPOSITION_THRESHOLD = -0.5
_PERSISTENCE_DECISIONS = (1, 3, 5)


def build_regime_opposition_episode(
    side: str,
    provider_evaluations: Sequence[Record],
    canonical_evaluations: Sequence[Record],
    *,
    entry_timestamp_ms: int,
    end_timestamp_ms: int,
) -> dict[str, object]:
    """Measure sustained causal opposition without supplying exit authority."""
    entry_ms = nonnegative_int(entry_timestamp_ms, "opposition entry timestamp")
    end_ms = nonnegative_int(end_timestamp_ms, "opposition end timestamp")
    if end_ms < entry_ms:
        raise ValueError("opposition episode ends before entry")
    provider = _evaluation_index(provider_evaluations, entry_ms, end_ms)
    canonical = _evaluation_index(canonical_evaluations, entry_ms, end_ms)
    observations = _observations(side, provider, canonical)
    summary = _persistence_summary(observations)
    return {
        "schema_version": 1,
        "mode": "causal_regime_opposition_persistence_v1",
        "contract": _contract(),
        "opposition_threshold": _OPPOSITION_THRESHOLD,
        "persistence_decisions": list(_PERSISTENCE_DECISIONS),
        "entry_timestamp_ms": entry_ms,
        "end_timestamp_ms": end_ms,
        **summary,
        "limitations": _limitations(),
    }


def _evaluation_index(
    evaluations: Sequence[Record], entry_ms: int, end_ms: int
) -> dict[int, Record]:
    output: dict[int, Record] = {}
    for evaluation in evaluations:
        if is_technical_unavailability(evaluation):
            continue
        timestamp_ms = nonnegative_int(
            evaluation.get("decision_time_ms"), "opposition decision timestamp"
        )
        if timestamp_ms % _DECISION_INTERVAL_MS:
            raise ValueError("opposition decisions must align to completed minutes")
        if timestamp_ms < entry_ms or timestamp_ms > end_ms:
            continue
        prior = output.get(timestamp_ms)
        if prior is not None and prior != evaluation:
            raise ValueError("conflicting duplicate opposition decision")
        output[timestamp_ms] = evaluation
    return output


def _observations(
    side: str,
    provider: Mapping[int, Record],
    canonical: Mapping[int, Record],
) -> list[tuple[int, float | None]]:
    observations: list[tuple[int, float | None]] = []
    for timestamp_ms in sorted(set(provider).union(canonical)):
        provider_value = provider.get(timestamp_ms)
        canonical_value = canonical.get(timestamp_ms)
        score = _support_score(side, provider_value, canonical_value)
        observations.append((timestamp_ms, score))
    return observations


def _support_score(
    side: str, provider: Record | None, canonical: Record | None
) -> float | None:
    if provider is None or canonical is None:
        return None
    contexts = {
        "signal_provider": {**provider, "status": "observed"},
        "canonical_regime": {**canonical, "status": "observed"},
    }
    value = build_regime_assessment(side, contexts).get("structure_support_score")
    return None if value is None else number(value, "opposition structure score")


def _persistence_summary(
    observations: Sequence[tuple[int, float | None]],
) -> dict[str, object]:
    summary = _threshold_persistence_summary(
        observations, _is_opposed, _PERSISTENCE_DECISIONS
    )
    return {
        "completed_decisions": summary["completed_decisions"],
        "unavailable_decisions": summary["unavailable_decisions"],
        "coverage_gap_decisions": summary["coverage_gap_decisions"],
        "opposed_decisions": summary["matched_decisions"],
        "first_opposed_decision_ms": summary["first_matched_decision_ms"],
        "last_decision_ms": summary["last_decision_ms"],
        "latest_structure_support_score": summary["latest_structure_support_score"],
        "maximum_consecutive_opposed": summary["maximum_consecutive"],
        "current_consecutive_opposed": summary["current_consecutive"],
        "current_active": summary["current_active"],
        "persistence_triggers": summary["persistence_triggers"],
    }


def _threshold_persistence_summary(
    observations: Sequence[tuple[int, float | None]],
    predicate: Callable[[float | None], bool],
    persistence_decisions: Sequence[int],
) -> dict[str, object]:
    opposed = 0
    current = 0
    maximum = 0
    gaps = 0
    triggers = {str(value): None for value in persistence_decisions}
    previous_ms: int | None = None
    first_matched_ms: int | None = None
    for timestamp_ms, score in observations:
        gaps += _gap_decisions(previous_ms, timestamp_ms)
        if (
            previous_ms is not None
            and timestamp_ms - previous_ms != _DECISION_INTERVAL_MS
        ):
            current = 0
        matched = predicate(score)
        current = current + 1 if matched else 0
        opposed += int(matched)
        if matched and first_matched_ms is None:
            first_matched_ms = timestamp_ms
        maximum = max(maximum, current)
        _record_triggers(triggers, persistence_decisions, current, timestamp_ms)
        previous_ms = timestamp_ms
    last_score = observations[-1][1] if observations else None
    return {
        "completed_decisions": len(observations),
        "unavailable_decisions": sum(score is None for _, score in observations),
        "coverage_gap_decisions": gaps,
        "matched_decisions": opposed,
        "first_matched_decision_ms": first_matched_ms,
        "last_decision_ms": previous_ms,
        "latest_structure_support_score": last_score,
        "maximum_consecutive": maximum,
        "current_consecutive": current,
        "current_active": predicate(last_score),
        "persistence_triggers": triggers,
    }


def _gap_decisions(previous_ms: int | None, timestamp_ms: int) -> int:
    if previous_ms is None:
        return 0
    return max(0, (timestamp_ms - previous_ms) // _DECISION_INTERVAL_MS - 1)


def _is_opposed(score: float | None) -> bool:
    return score is not None and score <= _OPPOSITION_THRESHOLD


def _record_triggers(
    triggers: dict[str, int | None],
    persistence_decisions: Sequence[int],
    current: int,
    timestamp_ms: int,
) -> None:
    for persistence in persistence_decisions:
        key = str(persistence)
        if current >= persistence and triggers[key] is None:
            triggers[key] = timestamp_ms


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _limitations() -> list[str]:
    return [
        "opposition uses fixed descriptive regime weights rather than fitted returns",
        "missing completed decisions break persistence sequences",
        "persistence timestamps are not executable fill prices or counterfactual PnL",
        "the journal cannot retain, close, resize, or mutate a live lifecycle",
    ]
