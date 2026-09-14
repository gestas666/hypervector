"""Recover a stable owned exit only after exact delayed protective-fill evidence."""

from collections.abc import Mapping
import math

from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_close_restart_context import READ_ONLY_RESTART_EVENTS
from hypervector.live.sol_execution_evidence import (
    QUANTITY_TOLERANCE,
    owned_fill_quantity,
)
from hypervector.live.sol_order_restart import SolOrderRestartError
from hypervector.live.sol_order_restart_context import (
    PendingPositionContext,
    pending_position_context,
)
from hypervector.live.sol_protective_checkpoint import (
    protective_progress_from_state,
    venue_without_credited_fills,
)
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionProgress,
)
from hypervector.live.sol_protective_journal import (
    validate_latest_protective_checkpoint,
)
from hypervector.live.sol_range_onset_live_journal_orders import intent_for_oid

UNRESOLVED_PROTECTIVE_EXIT = "protective exit history remains unresolved"
_RETRY_FAULTS = frozenset(
    {
        UNRESOLVED_PROTECTIVE_EXIT,
        "ambiguous local state FAULTED",
        "unknown venue order exists without local ownership",
    }
)
_IDENTITY_FIELDS = (
    "entry_oid",
    "stop_oid",
    "close_oid",
    "position_size_signed",
    "opened_at_ms",
    "execution_plan",
    "target_oid",
    "target_price",
)


def records_for_late_protective_exit(
    records: list[dict[str, object]], venue: SolReconciliationSnapshot
) -> list[dict[str, object]]:
    """Preserve a read-only fault's original OPEN context without rewriting the ledger."""
    start = _last_open_index(records)
    if start is None:
        return records
    fault = next(
        (i for i in range(start + 1, len(records)) if records[i].get("event_type") == "fault"),
        None,
    )
    if fault is None:
        return records
    context = pending_position_context(records[: start + 1], "OPEN")
    reason = _payload(records[fault]).get("reason")
    expected = (
        "flat reconciliation lacks a complete owned exit fill"
        if context.target_oid is not None
        else "continuous reconciliation failed: position size mismatch: "
        f"local={context.position_size_signed:g} venue=0"
    )
    if reason != expected:
        return records
    try:
        validate_latest_protective_checkpoint(records[: start + 1], intent_for_oid)
    except ValueError as exc:
        raise SolOrderRestartError(f"protective checkpoint validation failed: {exc}") from exc
    _validate_retry_suffix(records[start + 1 :], _payload(records[start]), expected)
    _require_complete_exit(context, venue)
    return records[:fault]


def _last_open_index(records: list[dict[str, object]]) -> int | None:
    for index in range(len(records) - 1, -1, -1):
        if records[index].get("event_type") != "state_transition":
            continue
        state = _payload(records[index]).get("state")
        if state not in {"FAULTED", "PREFLIGHT"}:
            return index if state == "OPEN" else None
    return None


def _validate_retry_suffix(
    records: list[dict[str, object]], original: Mapping[str, object], reason: str
) -> None:
    preflight = False
    allowed_faults = _RETRY_FAULTS | {reason}
    for row in records:
        kind = row.get("event_type")
        if kind in READ_ONLY_RESTART_EVENTS:
            continue
        payload = _payload(row)
        if kind == "fault" and payload.get("reason") in allowed_faults:
            continue
        if kind == "state_transition":
            state = payload.get("state")
            if state == "PREFLIGHT":
                preflight = True
            elif state != "FAULTED" or payload.get("last_fault") not in allowed_faults:
                raise SolOrderRestartError("protective restart has contradictory state evidence")
            expected = (
                {key: (0 if key == "position_size_signed" else None) for key in _IDENTITY_FIELDS}
                if preflight
                else original
            )
            progress = (
                ProtectiveExecutionProgress()
                if preflight
                else protective_progress_from_state(original)
            )
            if all(payload.get(key) == expected.get(key) for key in _IDENTITY_FIELDS) and (
                protective_progress_from_state(payload) == progress
            ):
                continue
        raise SolOrderRestartError("protective restart has contradictory later evidence")


def _require_complete_exit(
    context: PendingPositionContext, venue: SolReconciliationSnapshot
) -> None:
    venue = venue_without_credited_fills(venue, context.protective_progress)
    if context.stop_oid is None or context.stop_oid == context.target_oid:
        raise SolOrderRestartError("protective restart requires distinct owned order identities")
    owned = {context.stop_oid}
    if context.target_oid is not None:
        owned.add(context.target_oid)
    open_ids = [order.oid for order in venue.open_orders]
    if (
        venue.position.size_signed != 0.0
        or len(open_ids) != len(set(open_ids))
        or not set(open_ids).issubset(owned)
        or (context.target_oid is None and open_ids)
    ):
        raise SolOrderRestartError(UNRESOLVED_PROTECTIVE_EXIT)
    fills = [fill for fill in venue.fills if fill.oid in owned]
    if len({fill.trade_id for fill in fills}) != len(fills):
        raise SolOrderRestartError(UNRESOLVED_PROTECTIVE_EXIT)
    observed = {fill.oid for fill in fills}
    quantities = [
        owned_fill_quantity(
            venue,
            oid,
            position_size_signed=context.position_size_signed,
            entering=False,
            earliest_ms=context.opened_at_ms,
        )
        for oid in observed
    ]
    if any(size is None for size in quantities) or not math.isclose(
        math.fsum(size for size in quantities if size is not None),
        abs(context.position_size_signed),
        rel_tol=0.0,
        abs_tol=QUANTITY_TOLERANCE,
    ):
        raise SolOrderRestartError(UNRESOLVED_PROTECTIVE_EXIT)


def _payload(record: Mapping[str, object]) -> Mapping[str, object]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise SolOrderRestartError("protective restart payload must be an object")
    return value
