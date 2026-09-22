"""Append-first, lifecycle-bound adaptive exit observations and restart state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.live.cohort_durable_decisions import DecisionEmitter

ADAPTIVE_EVENT = "adaptive_exit_observation"


class AdaptiveExitJournal:
    """Retain the latest durable observation for each exact entry identity."""

    def __init__(self, records: Sequence[Mapping[str, object]], emit: DecisionEmitter) -> None:
        """Recover bounded per-lifecycle state and bind its append boundary."""
        self._latest: dict[str, dict[str, object]] = {}
        self._emit = emit
        for row in records:
            if row.get("event_type") == ADAPTIVE_EVENT:
                payload = row.get("payload")
                if not isinstance(payload, Mapping):
                    raise ValueError("adaptive journal payload must be an object")
                self._accept(payload)

    def recorded(self, lifecycle_id: str) -> Mapping[str, object] | None:
        """Return copied lifecycle evidence without exposing mutable state."""
        payload = self._latest.get(lifecycle_id)
        return None if payload is None else dict(payload)

    def append(self, payload: Mapping[str, object]) -> None:
        """Durably record before making a changed floor available to execution."""
        identity, stamp = _identity(payload)
        previous = self._latest.get(identity)
        if previous is not None:
            _, previous_stamp = _identity(previous)
            if stamp < previous_stamp or (stamp == previous_stamp and payload != previous):
                raise ValueError("adaptive journal observation conflicts with durable state")
            if payload == previous:
                return
        self._emit(ADAPTIVE_EVENT, payload)
        self._accept(payload)

    def _accept(self, payload: Mapping[str, object]) -> None:
        identity, stamp = _identity(payload)
        previous = self._latest.get(identity)
        if previous is not None and stamp <= _identity(previous)[1]:
            raise ValueError("adaptive journal must increase monotonically")
        self._latest[identity] = dict(payload)


def _identity(payload: Mapping[str, object]) -> tuple[str, int]:
    identity, stamp = payload.get("lifecycle_id"), payload.get("observed_ms")
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("adaptive journal requires a lifecycle_id")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp <= 0:
        raise ValueError("adaptive journal requires a positive observed_ms")
    return identity, stamp
