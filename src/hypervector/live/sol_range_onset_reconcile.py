"""Restart ownership reconciliation for the SOL live canary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Literal

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
)
from hypervector.live.hyperliquid_protocol import (
    SolOpenOrder,
    SolReconciliationSnapshot,
)
from hypervector.live.sol_range_onset_bracket import (
    complete_bracket_visible,
    owned_exit_reason,
)
from hypervector.live.sol_range_onset_engine_contract import is_ioc_no_fill_error
from hypervector.live.sol_protective_order import protective_stop_covers

_VENUE_MUTATION_INTENTS = frozenset({"order_intent", "cancel_intent"})


class SolStartupReconciliationError(RuntimeError):
    """Local ownership and authoritative venue state cannot be reconciled."""


@dataclass(frozen=True)
class RecoveredSolOwnership:
    """Locally recorded identity for one protected SOL position."""

    entry_oid: int
    stop_oid: int
    position_size_signed: float
    opened_at_ms: int
    execution_plan: BoundExecutionPlan | None = None
    target_oid: int | None = None
    target_price: float | None = None


@dataclass(frozen=True)
class SolStartupReconciliation:
    """Safe startup disposition after comparing ledger and venue state."""

    disposition: Literal[
        "flat",
        "restore_open",
        "protective_stop_filled",
        "owned_bracket_filled",
    ]
    ownership: RecoveredSolOwnership | None
    exit_reason: str | None = None


def reconcile_sol_startup(
    *,
    records: Sequence[Mapping[str, object]],
    venue: SolReconciliationSnapshot,
    expected_profile_fingerprint: str | None = None,
) -> SolStartupReconciliation:
    """Return a safe flat/open disposition or raise on ambiguous ownership."""
    scoped_records = _records_for_profile(records, expected_profile_fingerprint)
    local = _recover_local_state(scoped_records)
    if local is None:
        return _reconcile_without_open_ownership(venue)
    state, ownership = local
    preflight_fault = state == "FAULTED" and _is_preflight_only_fault(scoped_records)
    ioc_no_fill = state == "FAULTED" and _is_ioc_no_fill_fault(scoped_records)
    if (
        state in {"FLAT", "PREFLIGHT"}
        or (state == "STOPPED" and ownership is None)
        or preflight_fault
        or ioc_no_fill
    ):
        return _reconcile_without_open_ownership(venue)
    if state not in {"OPEN", "STOPPED"}:
        raise SolStartupReconciliationError(f"ambiguous local state {state}")
    if ownership is None:
        raise SolStartupReconciliationError(
            f"ambiguous local state {state}: protected ownership is incomplete"
        )
    bracket_reason = _owned_bracket_exit_reason(ownership, venue)
    if bracket_reason is not None:
        return SolStartupReconciliation(
            "owned_bracket_filled",
            ownership,
            bracket_reason,
        )
    if owned_protective_stop_fill(ownership, venue):
        return SolStartupReconciliation("protective_stop_filled", ownership)
    _verify_owned_position(ownership, venue)
    return SolStartupReconciliation("restore_open", ownership)


def _records_for_profile(
    records: Sequence[Mapping[str, object]],
    expected_profile_fingerprint: str | None,
) -> tuple[Mapping[str, object], ...]:
    if expected_profile_fingerprint is None:
        return tuple(records)
    if not expected_profile_fingerprint.strip():
        raise SolStartupReconciliationError("expected profile fingerprint must be non-empty")
    return tuple(
        record
        for record in records
        if record.get("profile_fingerprint") == expected_profile_fingerprint
    )


def _owned_bracket_exit_reason(
    ownership: RecoveredSolOwnership,
    venue: SolReconciliationSnapshot,
) -> str | None:
    if ownership.target_oid is None:
        return None
    return owned_exit_reason(
        venue,
        stop_oid=ownership.stop_oid,
        target_oid=ownership.target_oid,
        position_size_signed=ownership.position_size_signed,
    )


def _recover_local_state(
    records: Sequence[Mapping[str, object]],
) -> tuple[str, RecoveredSolOwnership | None] | None:
    for record in reversed(records):
        if record.get("event_type") != "state_transition":
            continue
        payload = _mapping(record.get("payload"), "state_transition payload")
        state = _text(payload.get("state"), "state")
        size = _number(payload.get("position_size_signed", 0.0), "position size")
        if state not in {"OPEN", "STOPPED", "FLAT"}:
            return state, None
        if size == 0.0:
            return state, None
        target_oid = _optional_positive_oid(payload.get("target_oid"), "target_oid")
        target_price = _optional_positive_number(payload.get("target_price"), "target_price")
        if (target_oid is None) != (target_price is None):
            raise SolStartupReconciliationError("target ownership requires both oid and price")
        ownership = RecoveredSolOwnership(
            entry_oid=_positive_oid(payload.get("entry_oid"), "entry_oid"),
            stop_oid=_positive_oid(payload.get("stop_oid"), "stop_oid"),
            position_size_signed=size,
            opened_at_ms=_nonnegative_integer(
                payload.get("opened_at_ms"),
                "opened_at_ms",
            ),
            execution_plan=_execution_plan(payload.get("execution_plan")),
            target_oid=target_oid,
            target_price=target_price,
        )
        return state, ownership
    return None


def _is_preflight_only_fault(records: Sequence[Mapping[str, object]]) -> bool:
    state_indexes = [
        index
        for index, record in enumerate(records)
        if record.get("event_type") == "state_transition"
    ]
    if len(state_indexes) < 2:
        return False
    previous_index, fault_index = state_indexes[-2:]
    previous = _mapping(
        records[previous_index].get("payload"),
        "state_transition payload",
    )
    if previous.get("state") != "PREFLIGHT":
        return False
    position_size = _number(
        previous.get("position_size_signed", 0.0),
        "position size",
    )
    if position_size != 0.0:
        return False
    intervening = records[previous_index + 1 : fault_index + 1]
    return not any(record.get("event_type") in _VENUE_MUTATION_INTENTS for record in intervening)


def _is_ioc_no_fill_fault(records: Sequence[Mapping[str, object]]) -> bool:
    state_indexes = [
        index
        for index, record in enumerate(records)
        if record.get("event_type") == "state_transition"
    ]
    if len(state_indexes) < 2:
        return False
    pending_index, fault_index = state_indexes[-2:]
    pending = _mapping(records[pending_index].get("payload"), "pending state")
    if pending.get("state") != "ENTRY_PENDING":
        return False
    relevant = [
        record
        for record in records[pending_index + 1 : fault_index]
        if record.get("event_type") in {"order_intent", "order_acknowledgement", "fault"}
    ]
    if [record.get("event_type") for record in relevant] != [
        "order_intent",
        "order_acknowledgement",
        "fault",
    ]:
        return False
    intent, acknowledgement, fault = (
        _mapping(record.get("payload"), "IOC no-fill evidence") for record in relevant
    )
    client_order_id = intent.get("client_order_id")
    error = acknowledgement.get("error")
    return bool(
        intent.get("operation") == "entry"
        and isinstance(client_order_id, str)
        and acknowledgement.get("operation") == "entry"
        and acknowledgement.get("accepted") is False
        and acknowledgement.get("oid") is None
        and acknowledgement.get("status") == "error"
        and acknowledgement.get("client_order_id") == client_order_id
        and isinstance(error, str)
        and is_ioc_no_fill_error(error)
        and fault.get("reason") == f"entry rejected: {error}"
    )


def _reconcile_without_open_ownership(
    venue: SolReconciliationSnapshot,
) -> SolStartupReconciliation:
    if venue.position.size_signed != 0.0:
        raise SolStartupReconciliationError("unknown venue exposure exists without local ownership")
    if venue.open_orders:
        raise SolStartupReconciliationError("unknown venue order exists without local ownership")
    return SolStartupReconciliation("flat", None)


def owned_protective_stop_fill(
    ownership: RecoveredSolOwnership,
    venue: SolReconciliationSnapshot,
) -> bool:
    """Verify that a flat venue was produced by the exact complete owned stop."""
    if venue.position.size_signed != 0.0 or venue.open_orders:
        return False
    expected_side = "A" if ownership.position_size_signed > 0.0 else "B"
    expected_direction = "close long" if ownership.position_size_signed > 0.0 else "close short"
    matching = [
        fill
        for fill in venue.fills
        if fill.oid == ownership.stop_oid
        and fill.side == expected_side
        and fill.direction.strip().lower() == expected_direction
    ]
    filled_size = sum(fill.size for fill in matching)
    return bool(matching) and math.isclose(
        filled_size,
        abs(ownership.position_size_signed),
        rel_tol=0.0,
        abs_tol=1e-9,
    )


def _verify_owned_position(
    ownership: RecoveredSolOwnership,
    venue: SolReconciliationSnapshot,
) -> None:
    observed_size = venue.position.size_signed
    if not math.isclose(
        observed_size,
        ownership.position_size_signed,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise SolStartupReconciliationError(
            "position size mismatch: "
            f"local={ownership.position_size_signed:g} venue={observed_size:g}"
        )
    matching = [order for order in venue.open_orders if order.oid == ownership.stop_oid]
    if not matching:
        raise SolStartupReconciliationError(f"protective stop {ownership.stop_oid} is missing")
    if ownership.target_oid is not None and ownership.target_price is not None:
        if not complete_bracket_visible(
            venue,
            stop_oid=ownership.stop_oid,
            target_oid=ownership.target_oid,
            position_size_signed=ownership.position_size_signed,
            target_price=ownership.target_price,
        ):
            raise SolStartupReconciliationError("owned stop/target bracket mismatch")
        return
    if len(venue.open_orders) != 1:
        raise SolStartupReconciliationError("unknown additional SOL order exists")
    _verify_stop(matching[0], ownership.position_size_signed)


def _verify_stop(order: SolOpenOrder, position_size_signed: float) -> None:
    if not order.reduce_only or not order.is_trigger:
        raise SolStartupReconciliationError("owned stop is not a reduce-only trigger")
    expected_side = "A" if position_size_signed > 0.0 else "B"
    if order.side != expected_side:
        raise SolStartupReconciliationError("protective stop side mismatch")
    if not protective_stop_covers(order, position_size_signed):
        raise SolStartupReconciliationError("protective stop size mismatch")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise SolStartupReconciliationError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SolStartupReconciliationError(f"{label} must be non-empty text")
    return value.strip()


def _number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise SolStartupReconciliationError(f"{label} must be numeric")
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise SolStartupReconciliationError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise SolStartupReconciliationError(f"{label} must be finite")
    return parsed


def _positive_oid(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SolStartupReconciliationError(f"{label} must be a positive integer")
    return value


def _optional_positive_oid(value: object, label: str) -> int | None:
    return None if value is None else _positive_oid(value, label)


def _nonnegative_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolStartupReconciliationError(f"{label} must be a nonnegative integer")
    return value


def _optional_positive_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    number = _number(value, label)
    if number <= 0.0:
        raise SolStartupReconciliationError(f"{label} must be positive")
    return number


def _execution_plan(value: object) -> BoundExecutionPlan | None:
    if value is None:
        return None
    try:
        return BoundExecutionPlan.from_payload(value)
    except CohortExecutionPlanError as exc:
        raise SolStartupReconciliationError(f"invalid persisted execution plan: {exc}") from exc
