"""Protective-stop attribution for read-only live lifecycle journals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

Record = Mapping[str, object]


def protective_stop_attribution(records: Sequence[Record]) -> dict[str, object] | None:
    """Return the latest accepted protective stop and its submitted trigger."""
    intents = _stop_intents(records)
    accepted = [
        record
        for record in records
        if record.get("event_type") == "stop_order"
        and _payload(record).get("operation") == "protective_stop"
        and _payload(record).get("accepted") is True
    ]
    if not accepted:
        return None
    payload = _payload(accepted[-1])
    client_id = _required_text(payload.get("client_order_id"), "stop client id")
    intent = intents.get(client_id)
    if intent is None:
        raise ValueError("accepted protective stop lacks its submitted intent")
    trigger = _required_positive_number(
        _payload(intent).get("trigger_price"), "protective-stop trigger"
    )
    return {
        "oid": _required_positive_integer(payload.get("oid"), "protective-stop oid"),
        "trigger_price": trigger,
    }


def _stop_intents(records: Sequence[Record]) -> dict[str, Record]:
    output: dict[str, Record] = {}
    for record in records:
        if record.get("event_type") != "order_intent":
            continue
        values = _payload(record)
        if values.get("operation") != "protective_stop":
            continue
        client_id = _required_text(values.get("client_order_id"), "stop client id")
        if client_id in output:
            raise ValueError("duplicate protective-stop client order id")
        output[client_id] = record
    return output


def _payload(record: Record) -> Record:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise ValueError("live journal protection payload must be an object")
    return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _required_positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _required_positive_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result
