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
_READINESS_SEED_REASON = "pre_activation_readiness_seed"
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
    side_source: str | None = None

    def __post_init__(self) -> None:
        """Default direct research fixtures to the declared decision boundary."""
        if self.available_time_ms == -1:
            object.__setattr__(self, "available_time_ms", self.decision_time_ms)
        if self.available_time_ms < self.decision_time_ms:
            raise ValueError("candidate availability cannot precede its decision")
        if self.side_source not in {
            None,
            "evaluation",
            "readiness",
            "single_configured_direction",
            "unavailable",
            "conflict",
        }:
            raise ValueError("candidate side source is invalid")


@dataclass(frozen=True)
class _ParsedCandidate:
    candidate: SignalCandidate
    direction_conflict: bool


def evaluation_candidates(
    records: Sequence[Record],
) -> tuple[tuple[SignalCandidate, ...], int, int]:
    """Return post-activation unique candidates, exclusions, and conflicts."""
    activation_times = _activation_times_ms(records)
    configured_sides = _configured_provider_sides(records)
    seen: dict[tuple[str | None, str, str, int], Record] = {}
    output: list[SignalCandidate] = []
    excluded = 0
    direction_conflicts = 0
    for row in event_rows(records, "intent_routing"):
        source_run_id = _source_run_id(row, activation_times)
        available_time_ms = int(timestamp(row).timestamp() * 1_000)
        for evaluation in object_list(payload(row), "evaluations", required=False):
            if is_technical_unavailability(evaluation):
                continue
            parsed = _candidate(
                evaluation,
                available_time_ms,
                source_run_id,
                configured_sides,
            )
            if evaluation.get("backend_non_action_reason") == _READINESS_SEED_REASON:
                continue
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


def _configured_provider_sides(
    records: Sequence[Record],
) -> dict[tuple[str | None, str, str], frozenset[str]]:
    result: dict[tuple[str | None, str, str], frozenset[str]] = {}
    for row in event_rows(records, "configuration_identity"):
        source_run_id = _optional_run_id(row)
        for provider in object_list(payload(row), "providers", required=False):
            if provider.get("sides") is None:
                continue
            strategy_id = text(provider.get("strategy_id"), "provider strategy id")
            symbols = text_list(provider.get("symbols"), "provider symbols")
            for symbol in symbols:
                key = (source_run_id, strategy_id, symbol)
                if key in result:
                    raise ValueError("duplicate configured provider-symbol direction")
                result[key] = _effective_provider_sides(provider, symbol)
    return result


def _effective_provider_sides(provider: Record, symbol: str) -> frozenset[str]:
    base = _validated_sides(provider.get("sides"), "provider sides")
    raw_overrides = provider.get("execution_side_overrides")
    if raw_overrides is None:
        return base
    override = mapping(raw_overrides, "provider execution side overrides").get(symbol)
    return base if override is None else _validated_sides(override, "side override")


def _validated_sides(value: object, label: str) -> frozenset[str]:
    values = text_list(value, label)
    if not values or len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique and non-empty")
    sides = frozenset(values)
    if not sides.issubset({"long", "short"}):
        raise ValueError(f"{label} must contain only long or short")
    return sides


def is_technical_unavailability(evaluation: Record) -> bool:
    """Validate and identify non-candidate provider outage telemetry."""
    if evaluation.get("decision_action") != "technical_unavailable":
        return False
    text(evaluation.get("strategy_id"), "unavailable strategy id")
    text(evaluation.get("symbol"), "unavailable symbol")
    nonnegative_int(evaluation.get("decision_time_ms"), "unavailable decision time")
    if number(evaluation.get("reference_price"), "unavailable reference price") <= 0:
        raise ValueError("unavailable reference price must be positive")
    reason = text(
        evaluation.get("backend_non_action_reason"),
        "unavailable backend reason",
    )
    if evaluation.get("eligible") is not False or evaluation.get("side") is not None:
        raise ValueError("technical unavailability cannot be execution eligible")
    if text(evaluation.get("reason"), "unavailable reason") != reason:
        raise ValueError("technical unavailability reasons disagree")
    readiness = mapping(evaluation.get("readiness"), "unavailable readiness")
    blockers = text_list(readiness.get("blockers"), "unavailable blockers")
    metrics = mapping(readiness.get("metrics"), "unavailable metrics")
    if reason not in blockers or metrics.get("technical_availability") != "unavailable":
        raise ValueError("technical unavailability contract is invalid")
    return True


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
    evaluation: Record,
    available_time_ms: int,
    source_run_id: str | None,
    configured_sides: Mapping[tuple[str | None, str, str], frozenset[str]],
) -> _ParsedCandidate:
    decision_ms = nonnegative_int(evaluation.get("decision_time_ms"), "decision time")
    if decision_ms % _MINUTE_MS:
        raise ValueError("provider decision time must align to a minute boundary")
    causal_available_ms = max(available_time_ms, decision_ms)
    readiness = mapping(evaluation.get("readiness"), "provider readiness")
    strategy_id = text(evaluation.get("strategy_id"), "strategy id")
    symbol = text(evaluation.get("symbol"), "evaluation symbol")
    evaluation_side = _optional_side(evaluation.get("side"), "evaluation side")
    readiness_side = _optional_side(readiness.get("side"), "readiness side")
    eligible = evaluation.get("eligible")
    if not isinstance(eligible, bool):
        raise ValueError("provider evaluation eligibility must be boolean")
    side, side_source, conflict = _resolved_side(
        evaluation_side,
        readiness_side,
        configured_sides.get((source_run_id, strategy_id, symbol)),
    )
    if eligible and conflict:
        raise ValueError("provider evaluation and readiness directions disagree")
    if eligible and evaluation_side is None:
        raise ValueError("eligible provider evaluation requires an execution side")
    reference = number(evaluation.get("reference_price"), "reference price")
    if reference <= 0.0:
        raise ValueError("provider reference price must be positive")
    return _ParsedCandidate(
        candidate=SignalCandidate(
            strategy_id=strategy_id,
            symbol=symbol,
            decision_time_ms=decision_ms,
            available_time_ms=causal_available_ms,
            reference_price=reference,
            side=side,
            eligible=eligible,
            blockers=tuple(text_list(readiness.get("blockers"), "readiness blockers")),
            metrics=_candidate_metrics(evaluation, readiness),
            source_run_id=source_run_id,
            side_source=side_source,
        ),
        direction_conflict=conflict,
    )


def _resolved_side(
    evaluation_side: str | None,
    readiness_side: str | None,
    configured_sides: frozenset[str] | None,
) -> tuple[str | None, str, bool]:
    if evaluation_side is not None and readiness_side not in {None, evaluation_side}:
        return None, "conflict", True
    if evaluation_side is not None:
        return evaluation_side, "evaluation", False
    if readiness_side is not None:
        return readiness_side, "readiness", False
    if configured_sides is not None and len(configured_sides) == 1:
        return next(iter(configured_sides)), "single_configured_direction", False
    return None, "unavailable", False


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
