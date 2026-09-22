"""Bounded recovery projection for cohort-level durable decisions."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.sol_range_onset_ledger import SolLiveLedger

_EVENT_TYPES = frozenset(
    {"maximum_hold_decision", "provider_exit_decision", "profit_lock_decision"}
)


def durable_decision_records(ledger: SolLiveLedger) -> list[dict[str, object]]:
    """Validate the complete ledger while retaining only durable decisions."""
    latest: dict[str, dict[str, object]] = {}

    def retain(record: Mapping[str, object]) -> bool:
        if record.get("event_type") != "adaptive_exit_observation":
            return _is_durable_decision(record)
        payload = record.get("payload")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("lifecycle_id"), str):
            raise ValueError("adaptive recovery record lacks lifecycle identity")
        latest[payload["lifecycle_id"]] = dict(record)
        return False

    records = ledger.read_matching(retain)
    return records + list(latest.values())


def _is_durable_decision(record: Mapping[str, object]) -> bool:
    return record.get("event_type") in _EVENT_TYPES
