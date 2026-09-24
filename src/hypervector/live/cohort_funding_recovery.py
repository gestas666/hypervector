"""Recover the inclusive funding boundary from exact-profile durable evidence."""

from __future__ import annotations

from datetime import datetime

from hypervector.live.cohort_funding_window import funding_window_from_payload
from hypervector.live.sol_range_onset_ledger import SolLiveLedger

_DAY_MS = 86_400_000
_RECOVERY_EVENTS = frozenset(
    {"configuration_identity", "funding_reconciliation_window"}
)


def recover_funding_cursor(
    ledger: SolLiveLedger, profile_fingerprint: str
) -> int | None:
    """Recover the last committed query, or the first known profile activation."""
    records = ledger.read_matching(
        lambda row: row.get("profile_fingerprint") == profile_fingerprint
        and row.get("event_type") in _RECOVERY_EVENTS,
        event_types=_RECOVERY_EVENTS,
        profile_fingerprint=profile_fingerprint,
    )
    if not records:
        return None
    for row in reversed(records):
        if row["event_type"] == "funding_reconciliation_window":
            return funding_window_from_payload(
                row.get("payload")
            ).committed_funding_end_time_ms
    value = records[0].get("observed_at_utc")
    if not isinstance(value, str):
        raise ValueError("funding recovery profile activation lacks a timestamp")
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("funding recovery profile activation must be timezone-aware")
    return int(observed.timestamp() * 1000)


def initial_funding_cursor(activation_ms: int, recovered_ms: int | None) -> int:
    """Cover unreconciled downtime while retaining the existing one-day overlap."""
    if type(activation_ms) is not int or activation_ms < 0:
        raise ValueError("funding activation timestamp must be a nonnegative integer")
    baseline = max(0, activation_ms - _DAY_MS)
    if recovered_ms is None:
        return baseline
    if type(recovered_ms) is not int or not 0 <= recovered_ms <= activation_ms:
        raise ValueError("recovered funding cursor must be between zero and activation")
    return min(baseline, recovered_ms)
