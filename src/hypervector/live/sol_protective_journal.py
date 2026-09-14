"""Attribute checkpointed partial exits to their durable orders and original fill rows."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict

from hypervector.live.hyperliquid_protocol import SolFill
from hypervector.live.sol_protective_checkpoint import protective_progress_from_state
from hypervector.live.sol_range_onset_live_journal_values import (
    payload,
    required_positive_int,
)

Record = Mapping[str, object]
IntentLookup = Callable[[Sequence[Record], int], Record | None]


def protective_checkpoint_exit_oids(records: Sequence[Record], lookup: IntentLookup) -> set[int]:
    """Require durable exit intents and exact economic rows for each credited receipt."""
    owned: set[int] = set()
    for index, row in enumerate(records):
        if row.get("event_type") != "state_transition":
            continue
        owned.update(_checkpoint_exit_oids(records[: index + 1], payload(row), lookup))
    return owned


def validate_latest_protective_checkpoint(records: Sequence[Record], lookup: IntentLookup) -> None:
    """Validate the checkpoint to be restored against preceding original ledger evidence."""
    for index in range(len(records) - 1, -1, -1):
        if records[index].get("event_type") == "state_transition":
            _checkpoint_exit_oids(records[: index + 1], payload(records[index]), lookup)
            return


def validate_protective_checkpoint_payload(
    records: Sequence[Record], body: Mapping[str, object], lookup: IntentLookup
) -> None:
    """Authenticate an explicit checkpoint against its preceding original ledger evidence."""
    _checkpoint_exit_oids(records, body, lookup)


def _checkpoint_exit_oids(
    records: Sequence[Record], body: Mapping[str, object], lookup: IntentLookup
) -> set[int]:
    progress = protective_progress_from_state(body)
    if not progress.fills:
        return set()
    _require_entry_owner(records, body)
    roles: set[str] = set()
    for fill in progress.fills:
        intent = lookup(records, fill.oid)
        role = payload(intent).get("operation") if intent is not None else None
        if role not in {"protective_stop", "target", "reduce_only_close"}:
            raise ValueError("checkpointed exit lacks its durable owned order intent")
        roles.add(str(role))
        _require_receipt(records, fill)
    if progress.stop_exit_required != ("protective_stop" in roles):
        raise ValueError("protective checkpoint stop-exit obligation conflicts with owned receipts")
    return {fill.oid for fill in progress.fills}


def _require_entry_owner(records: Sequence[Record], body: Mapping[str, object]) -> None:
    entry_oid = required_positive_int(body.get("entry_oid"), "checkpoint entry oid")
    matching = [
        row
        for row in records
        if row.get("event_type") == "order_acknowledgement"
        and payload(row).get("operation") in {"entry", "entry_restart_recovery"}
        and payload(row).get("accepted") is True
    ]
    if not matching or payload(matching[-1]).get("oid") != entry_oid:
        raise ValueError("protective checkpoint lacks this lifecycle's acknowledged entry")


def _require_receipt(records: Sequence[Record], fill: SolFill) -> None:
    matching = [
        payload(row)
        for row in records
        if row.get("event_type") == "fill" and payload(row).get("trade_id") == fill.trade_id
    ]
    expected = asdict(fill)
    expected["venue_timestamp_ms"] = expected.pop("timestamp_ms")
    if len(matching) != 1 or any(matching[0].get(key) != value for key, value in expected.items()):
        raise ValueError("checkpointed protective receipt conflicts with original fill evidence")
