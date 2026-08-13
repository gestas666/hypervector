"""Validated point-in-time provider candidates shared by cohort diagnostics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    mapping,
    nonnegative_int,
    number,
    object_list,
    payload,
    text,
    text_list,
    timestamp,
)

Record = Mapping[str, object]
_MINUTE_MS = 60_000
_REGIME_STATES = {"BREAKOUT", "RANGE", "TRANSITION", "TREND_DOWN", "TREND_UP"}
_REGIME_FIELDS = ("primary_regime", "state_1m", "state_5m", "context_15m")


@dataclass(frozen=True)
class SignalCandidate:
    """One deduplicated provider evaluation at its causal decision boundary."""

    strategy_id: str
    symbol: str
    decision_time_ms: int
    reference_price: float
    side: str | None
    eligible: bool
    blockers: tuple[str, ...]
    metrics: Mapping[str, object]
    available_time_ms: int = -1
    source_run_id: str | None = None

    def __post_init__(self) -> None:
        """Default direct research fixtures to the declared decision boundary."""
        if self.available_time_ms == -1:
            object.__setattr__(self, "available_time_ms", self.decision_time_ms)
        if self.available_time_ms < self.decision_time_ms:
            raise ValueError("candidate availability cannot precede its decision")


@dataclass(frozen=True)
class _ParsedCandidate:
    candidate: SignalCandidate
    direction_conflict: bool


def evaluation_candidates(
    records: Sequence[Record],
) -> tuple[tuple[SignalCandidate, ...], int, int]:
    """Return post-activation unique candidates, exclusions, and conflicts."""
    activation_times = _activation_times_ms(records)
    seen: dict[tuple[str | None, str, str, int], Record] = {}
    output: list[SignalCandidate] = []
    excluded = 0
    direction_conflicts = 0
    for row in event_rows(records, "intent_routing"):
        source_run_id = _source_run_id(row, activation_times)
        available_time_ms = int(timestamp(row).timestamp() * 1_000)
        for evaluation in object_list(payload(row), "evaluations", required=False):
            parsed = _candidate(evaluation, available_time_ms, source_run_id)
            candidate = parsed.candidate
            key = (
                source_run_id,
                candidate.strategy_id,
                candidate.symbol,
                candidate.decision_time_ms,
            )
            prior = seen.get(key)
            if prior is not None:
                if prior != evaluation:
                    raise ValueError("conflicting duplicate provider evaluation")
                continue
            seen[key] = evaluation
            if candidate.decision_time_ms <= activation_times[source_run_id]:
                excluded += 1
            else:
                output.append(candidate)
                direction_conflicts += parsed.direction_conflict
    return tuple(output), excluded, direction_conflicts


def _activation_times_ms(records: Sequence[Record]) -> dict[str | None, int]:
    identities = event_rows(records, "configuration_identity")
    if not identities:
        raise ValueError("forward diagnostics require configuration identity")
    values: dict[str | None, int] = {}
    for row in identities:
        source_run_id = _optional_run_id(row)
        if source_run_id in values:
            raise ValueError("forward diagnostics require one identity per run")
        values[source_run_id] = int(timestamp(row).timestamp() * 1_000)
    if None in values and len(values) != 1:
        raise ValueError("multi-run diagnostics require run ids on every identity")
    return values


def _source_run_id(
    row: Record, activation_times: Mapping[str | None, int]
) -> str | None:
    source_run_id = _optional_run_id(row)
    if source_run_id not in activation_times:
        raise ValueError("routing observation has no matching run identity")
    return source_run_id


def _optional_run_id(row: Record) -> str | None:
    value = row.get("run_id")
    if value is None:
        return None
    return text(value, "run_id")


def _candidate(
    evaluation: Record, available_time_ms: int, source_run_id: str | None
) -> _ParsedCandidate:
    decision_ms = nonnegative_int(evaluation.get("decision_time_ms"), "decision time")
    if decision_ms % _MINUTE_MS:
        raise ValueError("provider decision time must align to a minute boundary")
    causal_available_ms = max(available_time_ms, decision_ms)
    readiness = mapping(evaluation.get("readiness"), "provider readiness")
    evaluation_side = _optional_side(evaluation.get("side"), "evaluation side")
    readiness_side = _optional_side(readiness.get("side"), "readiness side")
    eligible = evaluation.get("eligible")
    if not isinstance(eligible, bool):
        raise ValueError("provider evaluation eligibility must be boolean")
    conflict = evaluation_side is not None and readiness_side not in {
        None,
        evaluation_side,
    }
    if eligible and conflict:
        raise ValueError("provider evaluation and readiness directions disagree")
    if eligible and evaluation_side is None:
        raise ValueError("eligible provider evaluation requires an execution side")
    reference = number(evaluation.get("reference_price"), "reference price")
    if reference <= 0.0:
        raise ValueError("provider reference price must be positive")
    return _ParsedCandidate(
        candidate=SignalCandidate(
            strategy_id=text(evaluation.get("strategy_id"), "strategy id"),
            symbol=text(evaluation.get("symbol"), "evaluation symbol"),
            decision_time_ms=decision_ms,
            available_time_ms=causal_available_ms,
            reference_price=reference,
            side=None if conflict else evaluation_side or readiness_side,
            eligible=eligible,
            blockers=tuple(text_list(readiness.get("blockers"), "readiness blockers")),
            metrics=_candidate_metrics(evaluation, readiness),
            source_run_id=source_run_id,
        ),
        direction_conflict=conflict,
    )


def _candidate_metrics(evaluation: Record, readiness: Record) -> dict[str, object]:
    metrics = dict(mapping(readiness.get("metrics", {}), "readiness metrics"))
    for field in _REGIME_FIELDS:
        state = evaluation.get(field)
        if state is None:
            continue
        if not isinstance(state, str) or state not in _REGIME_STATES:
            raise ValueError(f"provider {field} is invalid")
        embedded = metrics.get(field)
        if embedded is not None and embedded != state:
            if field == "state_5m":
                raise ValueError("provider five-minute state fields disagree")
            raise ValueError(f"provider {field} fields disagree")
        metrics[field] = state
    return metrics


def _optional_side(value: object, label: str) -> str | None:
    if value is None:
        return None
    side = text(value, label)
    if side not in {"long", "short"}:
        raise ValueError(f"{label} must be long, short, or null")
    return side
