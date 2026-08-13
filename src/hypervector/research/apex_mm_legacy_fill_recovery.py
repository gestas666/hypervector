"""Read-only venue identity recovery for legacy Apex MM fill journals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json

from hypervector.live.hyperliquid_protocol import SolFill


Record = Mapping[str, object]
MutableRecord = dict[str, object]

_FILL_FIELDS = {
    "oid": "oid",
    "venue_timestamp_ms": "timestamp_ms",
    "price": "price",
    "size": "size",
    "side": "side",
    "direction": "direction",
    "closed_pnl_usd": "closed_pnl_usd",
    "crossed": "crossed",
    "transaction_hash": "transaction_hash",
    "fee_usd": "fee_usd",
    "fee_token": "fee_token",
}
_LINKED_TIMESTAMPS = {
    "fee": "venue_timestamp_ms",
    "execution_quality": "fill_timestamp_ms",
    "fill_markout": "fill_timestamp_ms",
}


def recover_legacy_apex_fill_trade_ids(
    records: Sequence[Record],
    *,
    venue_fills: Sequence[SolFill],
    run_id: str,
) -> tuple[tuple[MutableRecord, ...], dict[str, object]]:
    """Enrich one legacy run using unique exact Hyperliquid venue-fill matches."""
    selected = [
        row
        for row in records
        if row.get("run_id") == run_id and row.get("event_type") == "fill"
    ]
    if not selected:
        raise ValueError(f"run {run_id} has no Apex fills to recover")
    matches = [_match_fill(row, venue_fills) for row in selected]
    identities = _identity_by_order_time(selected, matches)
    recovered = tuple(
        _enrich_record(row, run_id=run_id, identities=identities) for row in records
    )
    return recovered, _recovery_evidence(venue_fills, matches)


def _match_fill(record: Record, venue_fills: Sequence[SolFill]) -> SolFill:
    payload = _payload(record)
    exact = [fill for fill in venue_fills if _exact_match(payload, fill)]
    sequence = record.get("sequence")
    if not exact:
        raise ValueError(
            f"no exact venue fill matches legacy Apex fill sequence {sequence}"
        )
    if len(exact) > 1:
        raise ValueError(
            f"multiple exact venue fills match legacy Apex fill sequence {sequence}"
        )
    _require_consistent_trade_id(payload, exact[0].trade_id, sequence)
    return exact[0]


def _exact_match(payload: Mapping[str, object], fill: SolFill) -> bool:
    return all(
        payload.get(ledger_key) == getattr(fill, venue_key)
        for ledger_key, venue_key in _FILL_FIELDS.items()
    )


def _identity_by_order_time(
    records: Sequence[Record],
    matches: Sequence[SolFill],
) -> dict[tuple[int, int], int]:
    identities: dict[tuple[int, int], int] = {}
    for record, fill in zip(records, matches, strict=True):
        payload = _payload(record)
        key = (
            _required_int(payload, "oid"),
            _required_int(payload, "venue_timestamp_ms"),
        )
        existing = identities.get(key)
        if existing is not None and existing != fill.trade_id:
            raise ValueError(f"legacy Apex metrics are ambiguous for oid/time {key}")
        identities[key] = fill.trade_id
    return identities


def _enrich_record(
    record: Record,
    *,
    run_id: str,
    identities: Mapping[tuple[int, int], int],
) -> MutableRecord:
    cloned = dict(record)
    payload = dict(_payload(record))
    cloned["payload"] = payload
    if record.get("run_id") != run_id:
        return cloned
    event_type = record.get("event_type")
    if event_type == "fill":
        key = (
            _required_int(payload, "oid"),
            _required_int(payload, "venue_timestamp_ms"),
        )
        _set_trade_id(payload, identities[key], record.get("sequence"))
    elif isinstance(event_type, str) and _is_linked_metric(event_type, payload):
        trade_id = _linked_trade_id(event_type, payload, identities)
        _set_trade_id(payload, trade_id, record.get("sequence"))
    return cloned


def _is_linked_metric(event_type: str, payload: Mapping[str, object]) -> bool:
    return event_type in _LINKED_TIMESTAMPS and not (
        event_type == "fee" and payload.get("source") != "fill"
    )


def _linked_trade_id(
    event_type: str,
    payload: Mapping[str, object],
    identities: Mapping[tuple[int, int], int],
) -> int:
    timestamp_key = _LINKED_TIMESTAMPS[event_type]
    key = (_required_int(payload, "oid"), _required_int(payload, timestamp_key))
    trade_id = identities.get(key)
    if trade_id is None:
        raise ValueError(f"legacy Apex {event_type} has no exact run fill for {key}")
    return trade_id


def _set_trade_id(payload: MutableRecord, trade_id: int, sequence: object) -> None:
    _require_consistent_trade_id(payload, trade_id, sequence)
    payload["trade_id"] = trade_id


def _require_consistent_trade_id(
    payload: Mapping[str, object],
    trade_id: int,
    sequence: object,
) -> None:
    existing = payload.get("trade_id")
    if existing is not None and existing != trade_id:
        raise ValueError(f"legacy Apex sequence {sequence} has conflicting trade_id")


def _recovery_evidence(
    venue_fills: Sequence[SolFill],
    matches: Sequence[SolFill],
) -> dict[str, object]:
    venue_rows = sorted(
        (_venue_row(fill) for fill in venue_fills), key=lambda row: int(row["trade_id"])
    )
    serialized = json.dumps(venue_rows, separators=(",", ":"), sort_keys=True).encode()
    recovered = [
        {
            "trade_id": fill.trade_id,
            "oid": fill.oid,
            "venue_timestamp_ms": fill.timestamp_ms,
            "transaction_hash": fill.transaction_hash,
        }
        for fill in matches
    ]
    return {
        "source": "hyperliquid_mainnet_user_fills_read_only",
        "match_contract": "all_ledger_fill_fields_exact_v1",
        "recovered_fill_count": len(matches),
        "venue_result_count": len(venue_rows),
        "venue_result_sha256": hashlib.sha256(serialized).hexdigest(),
        "matches": recovered,
    }


def _venue_row(fill: SolFill) -> dict[str, object]:
    return {
        "trade_id": fill.trade_id,
        **{
            ledger_key: getattr(fill, venue_key)
            for ledger_key, venue_key in _FILL_FIELDS.items()
        },
    }


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"legacy Apex {key} must be an integer")
    return value


def _payload(record: Record) -> Mapping[str, object]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("legacy Apex record payload must be an object")
    return payload
