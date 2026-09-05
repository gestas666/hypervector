"""Report-only trigger state for source-bound first-event experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = Mapping[str, object]

_COUNTER_FIELDS = (
    "eligible_evaluations",
    "strategy_intents",
    "actions",
    "withheld",
    "fills",
    "open_lifecycles",
    "closed_trades",
)
_IDENTITY_FIELDS = ("run_id", "profile_id", "profile_fingerprint")


def build_first_event_observations(
    audit: Record,
    active_hypotheses: Sequence[Record],
) -> list[dict[str, object]]:
    """Compare source-bound baselines with the current causal audit prefix."""
    return [
        _observation(audit, row)
        for row in active_hypotheses
        if row.get("baseline_counters") is not None
    ]


def _observation(audit: Record, hypothesis: Record) -> dict[str, object]:
    identity = _identity(_mapping(audit.get("run"), "audit run"))
    baseline_identity = _identity(
        _mapping(hypothesis.get("baseline_identity"), "baseline identity")
    )
    hypothesis_id = _text(hypothesis.get("hypothesis_id"), "hypothesis identity")
    _validate_hypothesis(hypothesis)
    if identity != baseline_identity:
        return _identity_mismatch(hypothesis_id, baseline_identity, identity)
    baseline = _counters(hypothesis.get("baseline_counters"), "baseline counters")
    current = _current_counters(audit)
    deltas = _counter_deltas(baseline, current)
    escalations = _technical_escalations(deltas)
    return {
        "hypothesis_id": hypothesis_id,
        "status": _status(deltas, escalations),
        "baseline_identity_matches": True,
        "baseline_counters": baseline,
        "current_counters": current,
        "counter_deltas": deltas,
        "requires_immediate_audit": any(deltas.values()),
        "technical_escalation_required": bool(escalations),
        "technical_escalations": escalations,
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _current_counters(audit: Record) -> dict[str, int]:
    routing = _mapping(audit.get("routing"), "audit routing")
    entry_age = _mapping(routing.get("entry_age_diagnostics"), "entry-age diagnostics")
    execution = _mapping(audit.get("execution"), "audit execution")
    assets = _mapping(execution.get("by_asset"), "execution assets")
    return {
        "eligible_evaluations": _count(
            entry_age.get("eligible_evaluations"), "causal eligible evaluations"
        ),
        "strategy_intents": _count(routing.get("strategy_intents"), "intents"),
        "actions": _count(routing.get("actions"), "actions"),
        "withheld": _count(routing.get("withheld"), "withheld"),
        "fills": _count(execution.get("fills"), "fills"),
        "open_lifecycles": sum(
            _count(_mapping(row, "execution asset").get("open_lifecycles"), "open")
            for row in assets.values()
        ),
        "closed_trades": _count(execution.get("closed_trades"), "closed trades"),
    }


def _counter_deltas(
    baseline: Mapping[str, int], current: Mapping[str, int]
) -> dict[str, int]:
    deltas: dict[str, int] = {}
    for field in _COUNTER_FIELDS:
        delta = current[field] - baseline[field]
        if delta < 0:
            raise ValueError(f"{field} regressed below its baseline")
        deltas[field] = delta
    return deltas


def _technical_escalations(deltas: Record) -> list[str]:
    eligible = _count(deltas.get("eligible_evaluations"), "eligible delta")
    intents = _count(deltas.get("strategy_intents"), "intent delta")
    outcomes = _count(deltas.get("actions"), "action delta") + _count(
        deltas.get("withheld"), "withheld delta"
    )
    output: list[str] = []
    if eligible > intents:
        output.append("eligible_evaluation_without_strategy_intent")
    if intents > outcomes:
        output.append("strategy_intent_without_action_or_withholding")
    return output


def _status(deltas: Record, escalations: Sequence[str]) -> str:
    if escalations:
        return "technical_escalation_required"
    if _count(deltas.get("closed_trades"), "closed delta"):
        return "resolved_lifecycle_observed"
    if _count(deltas.get("fills"), "fill delta") or _count(
        deltas.get("open_lifecycles"), "open delta"
    ):
        return "open_lifecycle_observed"
    if _count(deltas.get("actions"), "action delta") or _count(
        deltas.get("withheld"), "withheld delta"
    ):
        return "eligible_outcome_observed"
    if _count(deltas.get("eligible_evaluations"), "eligible delta"):
        return "eligible_event_observed"
    return "awaiting_first_eligible_event"


def _identity_mismatch(
    hypothesis_id: str, expected: Record, observed: Record
) -> dict[str, object]:
    return {
        "hypothesis_id": hypothesis_id,
        "status": "baseline_identity_mismatch",
        "baseline_identity_matches": False,
        "expected_identity": dict(expected),
        "observed_identity": dict(observed),
        "requires_immediate_audit": True,
        "technical_escalation_required": True,
        "technical_escalations": ["baseline_identity_mismatch"],
        "execution_effect": "report_only",
        "automatic_live_change": False,
    }


def _validate_hypothesis(hypothesis: Record) -> None:
    if hypothesis.get("status") != "being_tested":
        raise ValueError("first-event hypothesis must be active")
    if hypothesis.get("execution_effect") != "report_only":
        raise ValueError("first-event hypothesis must be report-only")
    _text(hypothesis.get("decision_source"), "decision source")
    _text(hypothesis.get("evidence_baseline"), "evidence baseline")


def _identity(value: Record) -> dict[str, str]:
    return {field: _text(value.get(field), field) for field in _IDENTITY_FIELDS}


def _counters(value: object, label: str) -> dict[str, int]:
    source = _mapping(value, label)
    return {field: _count(source.get(field), field) for field in _COUNTER_FIELDS}


def _mapping(value: object, label: str) -> Record:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value
