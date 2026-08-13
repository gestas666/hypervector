"""Idempotent cohort decision journals backed by the append-only ledger."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

DecisionEmitter = Callable[[str, Mapping[str, object]], None]


class CohortDurableDecisionJournal:
    """Persist stable lifecycle decisions once and recover them after restart."""

    def __init__(
        self,
        *,
        records: Sequence[Mapping[str, object]],
        event_type: str,
        label: str,
        emit: DecisionEmitter,
    ) -> None:
        """Load one exact event type and bind its append boundary."""
        if not event_type.strip() or not label.strip():
            raise ValueError("durable decision event type and label are required")
        self._event_type = event_type
        self._label = label
        self._emit = emit
        self._decisions = _existing_decisions(records, event_type, label)

    def recorded(self, decision_id: str) -> Mapping[str, object] | None:
        """Return a copy of a prior decision by its stable lifecycle identity."""
        identity = _decision_id(decision_id, self._label)
        value = self._decisions.get(identity)
        return None if value is None else dict(value)

    def append_once(self, payload: Mapping[str, object]) -> None:
        """Append a new decision or accept an identical prior decision."""
        identity = _decision_id(payload.get("decision_id"), self._label)
        candidate = dict(payload)
        existing = self._decisions.get(identity)
        if existing is not None:
            if existing != candidate:
                raise ValueError(f"conflicting {self._label} decision: {identity}")
            return
        self._emit(self._event_type, candidate)
        self._decisions[identity] = candidate


def _existing_decisions(
    records: Sequence[Mapping[str, object]],
    event_type: str,
    label: str,
) -> dict[str, dict[str, object]]:
    decisions: dict[str, dict[str, object]] = {}
    for record in records:
        if record.get("event_type") != event_type:
            continue
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError(f"{label} ledger payload must be an object")
        identity = _decision_id(payload.get("decision_id"), label)
        if identity in decisions:
            raise ValueError(f"duplicate {label} decision_id: {identity}")
        decisions[identity] = dict(payload)
    return decisions


def _decision_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} decision_id must be non-empty")
    return value.strip()
