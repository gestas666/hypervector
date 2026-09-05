"""Authenticated raw-ledger accounting for one exact V58 live close."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose

from hypervector.research.cohort_lifecycle_evidence import build_fill_index
from hypervector.research.cohort_live_audit_values import mapping, number, payload, text

Record = Mapping[str, object]


@dataclass(frozen=True)
class LiveCloseLedger:
    """Exact scoped ledger rows and reconciled venue order identities."""

    rows: tuple[Record, ...]
    entry_oid: int
    exit_oid: int


@dataclass(frozen=True)
class LiveEntryLedger:
    """Exact scoped ledger rows and authenticated entry accounting."""

    rows: tuple[Record, ...]
    entry_oid: int
    entry_fill_count: int
    entry_fee_usd: float


@dataclass(frozen=True)
class LiveLedgerIdentity:
    """One exact run and asset-profile identity in an adopted lifecycle."""

    run_id: str
    profile_id: str
    profile_fingerprint: str


def reconcile_live_entry_ledger(
    rows: Sequence[Record],
    entry: Record,
    *,
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    symbol: str,
    side: str,
) -> LiveEntryLedger:
    """Authenticate one still-open V58 lifecycle's entry fill and fee."""
    direction = _side(side)
    scoped = _scoped_rows(rows, run_id, profile_id, profile_fingerprint)
    entry_oid = _entry_oid(entry, symbol)
    leg = mapping(entry.get("entry"), "entry")
    fills = build_fill_index({symbol: scoped})
    aggregate = fills.get((symbol, entry_oid))
    if aggregate is None:
        raise ValueError("V58 live close entry fill differs")
    _require_fill_aggregate(aggregate.size, aggregate.notional_usd, leg, "entry")
    _require_fill_event_contract(
        scoped, entry_oid, leg, f"Open {direction.title()}", "entry"
    )
    expected = _fill_fee_index(scoped, {entry_oid})
    observed = _fee_event_index(scoped, {entry_oid})
    if observed != expected:
        raise ValueError("V58 live close ledger fee identity differs")
    return LiveEntryLedger(
        scoped,
        entry_oid,
        len(fill_events(scoped, entry_oid)),
        sum(value[2] for value in observed.values()),
    )


def reconcile_live_close_ledger(
    rows: Sequence[Record],
    close: Record,
    *,
    run_id: str,
    profile_id: str,
    profile_fingerprint: str,
    symbol: str,
    side: str,
) -> LiveCloseLedger:
    """Reconcile exact-run fills, funding, and fees for one symbol and side."""
    return reconcile_live_close_ledger_epochs(
        rows,
        close,
        identities=(LiveLedgerIdentity(run_id, profile_id, profile_fingerprint),),
        symbol=symbol,
        side=side,
    )


def reconcile_live_close_ledger_epochs(
    rows: Sequence[Record],
    close: Record,
    *,
    identities: Sequence[LiveLedgerIdentity],
    symbol: str,
    side: str,
) -> LiveCloseLedger:
    """Reconcile an entry and exit spanning authenticated runtime epochs."""
    direction = _side(side)
    scoped = _scoped_identity_rows(rows, identities)
    entry_oid = _entry_oid(close, symbol)
    exit_oid = _exit_oid(scoped, close, direction)
    _reconcile_fills(scoped, close, entry_oid, exit_oid, symbol, direction)
    _reconcile_funding(scoped, close)
    _reconcile_fees(scoped, close, entry_oid, exit_oid)
    return LiveCloseLedger(scoped, entry_oid, exit_oid)


def fill_events(rows: Sequence[Record], oid: int) -> tuple[Record, ...]:
    """Return deduplicated exact fill rows for one venue order identity."""
    by_trade_id: dict[int, Record] = {}
    for row in rows:
        if row.get("event_type") != "fill" or payload(row).get("oid") != oid:
            continue
        trade_id = _positive_int(payload(row).get("trade_id"), "fill trade id")
        prior = by_trade_id.get(trade_id)
        if prior is not None and dict(payload(prior)) != dict(payload(row)):
            raise ValueError("V58 live close fill trade identity conflicts")
        by_trade_id[trade_id] = row
    return tuple(by_trade_id.values())


def fill_time(rows: Sequence[Record]) -> int:
    """Return the last venue timestamp among an order's exact fill rows."""
    if not rows:
        raise ValueError("V58 live close has no exit fill")
    return max(_fill_event_time(row) for row in rows)


def _scoped_rows(
    rows: Sequence[Record], run_id: str, profile_id: str, profile_fingerprint: str
) -> tuple[Record, ...]:
    identity = LiveLedgerIdentity(run_id, profile_id, profile_fingerprint)
    return _scoped_identity_rows(rows, (identity,))


def _scoped_identity_rows(
    rows: Sequence[Record], identities: Sequence[LiveLedgerIdentity]
) -> tuple[Record, ...]:
    expected = {
        (identity.run_id, identity.profile_id, identity.profile_fingerprint)
        for identity in identities
    }
    if not expected or len(expected) != len(identities):
        raise ValueError("V58 live close ledger identities are empty or duplicated")
    run_ids = {identity[0] for identity in expected}
    scoped = tuple(row for row in rows if row.get("run_id") in run_ids)
    if not scoped:
        raise ValueError("V58 live close ledger has no frozen-run rows")
    observed = {
        (
            text(row.get("run_id"), "run id"),
            text(row.get("profile_id"), "asset profile id"),
            text(row.get("profile_fingerprint"), "asset fingerprint"),
        )
        for row in scoped
    }
    if observed != expected:
        raise ValueError("V58 live close ledger profile identity differs")
    return scoped


def _reconcile_fills(
    rows: Sequence[Record],
    close: Record,
    entry_oid: int,
    exit_oid: int,
    symbol: str,
    side: str,
) -> None:
    fills = build_fill_index({symbol: rows})
    entry = mapping(close.get("entry"), "entry")
    exit_leg = mapping(close.get("exit"), "exit")
    entry_fill = fills.get((symbol, entry_oid))
    exit_fill = fills.get((symbol, exit_oid))
    if entry_fill is None:
        raise ValueError("V58 live close entry fill differs")
    if exit_fill is None:
        raise ValueError("V58 live close exit fill differs")
    _require_fill_aggregate(entry_fill.size, entry_fill.notional_usd, entry, "entry")
    _require_fill_aggregate(exit_fill.size, exit_fill.notional_usd, exit_leg, "exit")
    _require_fill_event_contract(
        rows, entry_oid, entry, f"Open {side.title()}", "entry"
    )
    _require_fill_event_contract(
        rows, exit_oid, exit_leg, f"Close {side.title()}", "exit"
    )
    gross = number(close.get("gross_market_pnl_usd"), "gross PnL")
    if not isclose(exit_fill.closed_pnl_usd, gross, abs_tol=1e-8):
        raise ValueError("V58 live close fill gross PnL differs")


def _require_fill_aggregate(
    size: float, notional_usd: float, leg: Record, label: str
) -> None:
    expected_size = _positive(leg.get("size"), f"{label} size")
    expected_price = _positive(leg.get("price"), f"{label} price")
    if not isclose(size, expected_size, abs_tol=1e-12):
        raise ValueError(f"V58 live close {label} fill differs")
    if not isclose(notional_usd / size, expected_price, abs_tol=1e-10):
        raise ValueError(f"V58 live close {label} fill differs")


def _require_fill_event_contract(
    rows: Sequence[Record], oid: int, leg: Record, direction: str, label: str
) -> None:
    fills = fill_events(rows, oid)
    if not fills or any(payload(row).get("direction") != direction for row in fills):
        raise ValueError(f"V58 live close {label} fill differs")
    expected_ms = _positive_int(leg.get("venue_timestamp_ms"), f"{label} time")
    if min(_fill_event_time(row) for row in fills) != expected_ms:
        raise ValueError(f"V58 live close {label} fill differs")


def _reconcile_funding(rows: Sequence[Record], close: Record) -> None:
    entry = mapping(close.get("entry"), "entry")
    exit_leg = mapping(close.get("exit"), "exit")
    entry_ms = _positive_int(entry.get("venue_timestamp_ms"), "entry time")
    exit_ms = _positive_int(exit_leg.get("venue_timestamp_ms"), "exit time")
    if exit_ms < entry_ms:
        raise ValueError("V58 live close exit precedes entry")
    funding = sum(_funding_value(row, entry_ms, exit_ms) for row in rows)
    if not isclose(funding, number(close.get("funding_usd"), "funding"), abs_tol=1e-8):
        raise ValueError("V58 live close ledger funding differs")


def _funding_value(row: Record, entry_ms: int, exit_ms: int) -> float:
    if row.get("event_type") != "funding":
        return 0.0
    values = payload(row)
    timestamp = _positive_int(values.get("venue_timestamp_ms"), "funding time")
    if not entry_ms <= timestamp <= exit_ms:
        return 0.0
    return number(values.get("usdc_delta"), "funding cashflow")


def _reconcile_fees(
    rows: Sequence[Record], close: Record, entry_oid: int, exit_oid: int
) -> None:
    oids = {entry_oid, exit_oid}
    expected = _fill_fee_index(rows, oids)
    observed = _fee_event_index(rows, oids)
    if observed != expected:
        raise ValueError("V58 live close ledger fee identity differs")
    total = sum(value[2] for value in observed.values())
    if not isclose(total, _nonnegative(close.get("fees_usd"), "fees"), abs_tol=1e-8):
        raise ValueError("V58 live close ledger fees differ")


def _entry_oid(close: Record, symbol: str) -> int:
    lifecycle = text(close.get("lifecycle_id"), "lifecycle id")
    prefix, separator, suffix = lifecycle.rpartition(":")
    if prefix != symbol or separator != ":" or not suffix.isdigit():
        raise ValueError("V58 live close lifecycle order identity differs")
    return _declared_or_derived_oid(
        mapping(close.get("entry"), "entry"), int(suffix), "entry"
    )


def _exit_oid(rows: Sequence[Record], close: Record, side: str) -> int:
    exit_leg = mapping(close.get("exit"), "exit")
    timestamp = _positive_int(exit_leg.get("venue_timestamp_ms"), "exit time")
    direction = f"Close {side.title()}"
    candidates = {
        _positive_int(payload(row).get("oid"), "exit oid")
        for row in rows
        if row.get("event_type") == "fill"
        and payload(row).get("direction") == direction
        and payload(row).get("venue_timestamp_ms") == timestamp
    }
    if len(candidates) != 1:
        raise ValueError("V58 live close exit order identity is ambiguous")
    return _declared_or_derived_oid(exit_leg, candidates.pop(), "exit")


def _declared_or_derived_oid(leg: Record, derived: int, label: str) -> int:
    declared = leg.get("oid")
    if declared is not None and _positive_int(declared, f"{label} oid") != derived:
        raise ValueError(f"V58 live close {label} order identity differs")
    return derived


def _fill_fee_index(
    rows: Sequence[Record], oids: set[int]
) -> dict[int, tuple[int, int, float]]:
    output: dict[int, tuple[int, int, float]] = {}
    for row in rows:
        if row.get("event_type") != "fill":
            continue
        values = payload(row)
        if values.get("oid") not in oids:
            continue
        trade_id = _positive_int(values.get("trade_id"), "fill trade id")
        output[trade_id] = _fill_fee_identity(values)
    return output


def _fee_event_index(
    rows: Sequence[Record], oids: set[int]
) -> dict[int, tuple[int, int, float]]:
    output: dict[int, tuple[int, int, float]] = {}
    for row in rows:
        if row.get("event_type") != "fee":
            continue
        values = payload(row)
        if values.get("source") != "fill" or values.get("oid") not in oids:
            continue
        trade_id = _positive_int(values.get("trade_id"), "fee trade id")
        if trade_id in output:
            raise ValueError("V58 live close ledger has duplicate fill fees")
        output[trade_id] = _fill_fee_identity(values)
    return output


def _fill_fee_identity(values: Record) -> tuple[int, int, float]:
    return (
        _positive_int(values.get("oid"), "fee oid"),
        _positive_int(values.get("venue_timestamp_ms"), "fee time"),
        _nonnegative(values.get("fee_usd"), "fill fee"),
    )


def _fill_event_time(row: Record) -> int:
    return _positive_int(payload(row).get("venue_timestamp_ms"), "fill time")


def _side(value: object) -> str:
    if value not in {"long", "short"}:
        raise ValueError("V58 live close side must be long or short")
    return str(value)


def _positive(value: object, label: str) -> float:
    output = number(value, label)
    if output <= 0.0:
        raise ValueError(f"V58 live close {label} must be positive")
    return output


def _nonnegative(value: object, label: str) -> float:
    output = number(value, label)
    if output < 0.0:
        raise ValueError(f"V58 live close {label} must be nonnegative")
    return output


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"V58 live close {label} must be a positive integer")
    return value
