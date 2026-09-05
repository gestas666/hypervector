"""Runtime health projection for the report-only cohort audit."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    integer,
    latest,
    payload,
    text,
    timestamp,
)

Record = Mapping[str, object]


def health_summary(
    records: Sequence[Record],
    assets: Mapping[str, Sequence[Record]],
) -> dict[str, object]:
    """Summarize terminal state, venue-stop coverage, and recorded faults."""
    runtime = _runtime_health(records)
    summaries = {symbol: _asset_health(rows) for symbol, rows in assets.items()}
    return {
        "faults": integer(runtime, "faults")
        + sum(integer(values, "faults") for values in summaries.values()),
        "runtime": runtime,
        "assets": summaries,
    }


def _runtime_health(records: Sequence[Record]) -> dict[str, object]:
    faults = event_rows(records, "runtime_fault")
    latest_fault = _runtime_fault(faults[-1]) if faults else None
    return {"faults": len(faults), "latest_fault": latest_fault}


def _runtime_fault(record: Record) -> dict[str, object]:
    values = payload(record)
    if values.get("status") != "faulted":
        raise ValueError("runtime fault status must be faulted")
    orders_attempted = values.get("orders_attempted")
    if not isinstance(orders_attempted, bool):
        raise ValueError("runtime fault orders_attempted must be boolean")
    timestamp(record)
    observed_at = text(record.get("observed_at_utc"), "observed_at_utc")
    return {
        "exception_type": text(values.get("exception_type"), "exception_type"),
        "observed_at_utc": observed_at,
        "orders_attempted": orders_attempted,
    }


def _asset_health(records: Sequence[Record]) -> dict[str, object]:
    transition = latest(records, "state_transition")
    position = latest(records, "position")
    reconciliation = latest(records, "reconciliation")
    state = payload(transition).get("state") if transition else None
    size = payload(position).get("size_signed") if position else None
    orders = payload(reconciliation).get("open_order_ids") if reconciliation else None
    stop_oid = payload(transition).get("stop_oid") if transition else None
    nonflat = (
        isinstance(size, (int, float)) and not isinstance(size, bool) and size != 0
    )
    protected = not nonflat or (
        isinstance(stop_oid, int) and isinstance(orders, list) and stop_oid in orders
    )
    faults = event_rows(records, "fault")
    return {
        "final_state": state,
        "position_size_signed": size,
        "open_order_ids": orders,
        "stop_oid": stop_oid,
        "protected_if_open": protected,
        "stop_reason": payload(transition).get("stop_reason") if transition else None,
        "faults": len(faults),
        "fault_reasons": [payload(row).get("reason") for row in faults],
    }
