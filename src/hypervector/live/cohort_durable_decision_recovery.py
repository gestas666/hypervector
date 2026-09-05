"""Bounded recovery projection for cohort-level durable decisions."""

from __future__ import annotations

from collections.abc import Mapping

from hypervector.live.sol_range_onset_ledger import SolLiveLedger

_EVENT_TYPES = frozenset(
    {"maximum_hold_decision", "provider_exit_decision", "profit_lock_decision"}
)


def durable_decision_records(ledger: SolLiveLedger) -> list[dict[str, object]]:
    """Validate the complete ledger while retaining only durable decisions."""
    return ledger.read_matching(_is_durable_decision)


def _is_durable_decision(record: Mapping[str, object]) -> bool:
    return record.get("event_type") in _EVENT_TYPES
