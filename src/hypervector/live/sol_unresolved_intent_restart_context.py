"""Retire failed startups that halted only on ambiguous unresolved order intents."""

from collections.abc import Mapping

from hypervector.live.sol_close_restart_context import READ_ONLY_RESTART_EVENTS
from hypervector.live.sol_order_restart import (
    MULTIPLE_UNRESOLVED_INTENTS,
    SolOrderRestartError,
)

_EMPTY_OWNERSHIP: Mapping[str, object] = {
    "entry_oid": None,
    "stop_oid": None,
    "target_oid": None,
    "close_oid": None,
    "position_size_signed": 0,
    "opened_at_ms": None,
    "execution_plan": None,
    "target_price": None,
}
_EMPTY_PROGRESS: Mapping[str, object] = {"fills": [], "stop_exit_required": False}


def records_before_unresolved_intent_startup_fault(
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return the view the first such failed startup saw, without rewriting the ledger.

    A startup that faults on ``MULTIPLE_UNRESOLVED_INTENTS`` stops while reducing
    the journal, after preflight and before any recovery or venue mutation. Only a
    trailing run of exactly such attempts (read-only telemetry, ownership-free
    PREFLIGHT/FAULTED states and that single fault reason) is removed; any other
    later evidence leaves the history unchanged for the existing fail-closed paths.
    """
    cut: int | None = None
    for index in range(len(records) - 1, -1, -1):
        row = records[index]
        if not _failed_startup_row(row):
            break
        if (
            row.get("event_type") == "state_transition"
            and _payload(row).get("state") == "PREFLIGHT"
        ):
            cut = index
    if cut is None or not any(
        row.get("event_type") == "fault" for row in records[cut:]
    ):
        return records
    return records[:cut]


def _failed_startup_row(row: Mapping[str, object]) -> bool:
    kind = row.get("event_type")
    if kind in READ_ONLY_RESTART_EVENTS:
        return True
    body = _payload(row)
    if kind == "fault":
        return body.get("reason") == MULTIPLE_UNRESOLVED_INTENTS
    if kind != "state_transition":
        return False
    state = body.get("state")
    if state == "FAULTED":
        if body.get("last_fault") != MULTIPLE_UNRESOLVED_INTENTS:
            return False
    elif state != "PREFLIGHT":
        return False
    return all(body.get(key) == value for key, value in _EMPTY_OWNERSHIP.items()) and (
        body.get("protective_progress", _EMPTY_PROGRESS) == _EMPTY_PROGRESS
    )


def _payload(row: Mapping[str, object]) -> Mapping[str, object]:
    value = row.get("payload")
    if not isinstance(value, Mapping):
        raise SolOrderRestartError("failed startup restart payload must be an object")
    return value
