"""Attribute durable entry/restart identities and every confirmed exit order."""

from collections.abc import Mapping, Sequence
from hypervector.live.sol_protective_journal import protective_checkpoint_exit_oids

from hypervector.live.sol_range_onset_live_journal_values import (
    optional_positive_float,
    payload,
    positive_int,
    required_float,
    required_positive_int,
    sequence,
)

Record = Mapping[str, object]


def accepted_entry_acks(records: Sequence[Record]) -> list[Record]:
    """Include restart-only acknowledgements and count an exact entry order once."""
    entries: dict[int, Record] = {}
    for record in records:
        body = payload(record)
        oid = positive_int(body.get("oid"))
        if (
            record.get("event_type") != "order_acknowledgement"
            or body.get("operation") not in {"entry", "entry_restart_recovery"}
            or body.get("accepted") is not True
            or oid is None
        ):
            continue
        if oid in entries:
            previous = payload(entries[oid]).get("client_order_id")
            current = body.get("client_order_id")
            if previous is not None and current is not None and previous != current:
                raise ValueError("live journal entry order has conflicting client identities")
        else:
            entries[oid] = record
    return list(entries.values())


def intent_for_ack(records: Sequence[Record], ack: Record) -> Record | None:
    """Resolve the durable request preceding one client-identified acknowledgement."""
    client_id = payload(ack).get("client_order_id")
    if not isinstance(client_id, str):
        return None
    return next(
        (
            record
            for record in reversed(records[: sequence(ack) - 1])
            if record.get("event_type") == "order_intent"
            and payload(record).get("client_order_id") == client_id
        ),
        None,
    )


def intent_for_oid(records: Sequence[Record], oid: int) -> Record | None:
    """Resolve an exact order's first client-identified acknowledgement and request."""
    ack = next(
        (
            record
            for record in records
            if record.get("event_type")
            in {"close", "stop_order", "target_order", "order_acknowledgement"}
            and payload(record).get("oid") == oid
            and isinstance(payload(record).get("client_order_id"), str)
        ),
        None,
    )
    return intent_for_ack(records, ack) if ack is not None else None


def partial_exit_oids(records: Sequence[Record]) -> set[int]:
    """Select only explicitly verified partial reductions with durable close ownership."""
    owned = protective_checkpoint_exit_oids(records, intent_for_oid)
    for record in records:
        body = payload(record)
        if record.get("event_type") != "close" or body.get("partial") is not True:
            continue
        if body.get("verified_flat") is not False:
            raise ValueError("live journal partial close must retain nonflat exposure")
        oid = required_positive_int(body.get("oid"), "partial close oid")
        intent = intent_for_oid(records, oid)
        if intent is None or payload(intent).get("operation") != "reduce_only_close":
            raise ValueError("live journal partial close lacks its durable close intent")
        owned.add(oid)
    return owned


def exit_order_ids(close_event: Record, window: Sequence[Record]) -> list[int]:
    """Union confirmed partial closes with the exact final close or bracket identities."""
    owned = partial_exit_oids(window)
    direct = positive_int(payload(close_event).get("oid"))
    if direct is not None:
        owned.add(direct)
    else:
        final = payload(close_event).get("owned_oids")
        if not isinstance(final, list):
            raise ValueError("live journal bracket close owned_oids must be a list")
        owned.update(required_positive_int(oid, "owned oid") for oid in final)
    filled = {
        required_positive_int(payload(row).get("oid"), "fill oid")
        for row in window
        if row.get("event_type") == "fill"
    }
    return sorted(owned & filled)


def close_fill_records(
    window: Sequence[Record], owned: Sequence[int] | set[int], direction: str
) -> list[Record]:
    """Reject contradictory directions while selecting every exact owned exit fill."""
    selected = [
        row
        for row in window
        if row.get("event_type") == "fill" and payload(row).get("oid") in owned
    ]
    for row in selected:
        if str(payload(row).get("direction", "")).strip().lower() != f"close {direction}":
            raise ValueError("live journal owned exit fill has the wrong direction")
    return selected


def weighted_exit_reference(records: Sequence[Record], fills: Sequence[Record]) -> float | None:
    """Weight each exit's own decision reference by its executed quantity."""
    quote = quantity = 0.0
    for fill in fills:
        oid = required_positive_int(payload(fill).get("oid"), "exit fill oid")
        body = payload(intent_for_oid(records, oid))
        reference = optional_positive_float(
            body.get("mark_price") or body.get("trigger_price") or body.get("limit_price")
        )
        if reference is None:
            return None
        size = required_float(payload(fill).get("size"))
        if size <= 0.0:
            raise ValueError("live journal exit fill size must be positive")
        quote += reference * size
        quantity += size
    return quote / quantity if quantity else None
