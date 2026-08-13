"""Exact identity helpers for Hyperliquid account-fill lifecycle records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypervector.live.hyperliquid_protocol import SolFill

type FillKey = tuple[int, int, int]


class HyperliquidFillIdentityError(ValueError):
    """A venue or ledger fill lacks a usable Hyperliquid trade ID."""


def require_trade_id(value: object, *, label: str) -> int:
    """Return one positive Hyperliquid trade ID or fail closed."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HyperliquidFillIdentityError(f"{label} must be a positive integer")
    return value


def fill_trade_id(fill: SolFill) -> int:
    """Return the exact venue identity of one normalized user fill."""
    return require_trade_id(fill.trade_id, label="fill trade_id")


def ledger_trade_id(payload: Mapping[str, object], *, label: str) -> int:
    """Read one exact venue trade ID from an append-only ledger payload."""
    return require_trade_id(payload.get("trade_id"), label=label)


def ledger_fill_key(
    payload: Mapping[str, object],
    *,
    timestamp_key: str,
    label: str,
) -> FillKey:
    """Return exact trade, order, and exchange-time identity for one fill row."""
    trade_id = ledger_trade_id(payload, label=f"{label} trade_id")
    oid = require_trade_id(payload.get("oid"), label=f"{label} oid")
    timestamp = require_trade_id(
        payload.get(timestamp_key),
        label=f"{label} {timestamp_key}",
    )
    return trade_id, oid, timestamp


def ledger_fill_keys(
    records: Sequence[Mapping[str, object]],
    *,
    timestamp_key: str,
    label: str,
) -> set[FillKey]:
    """Return exact unique fill identities from already-selected ledger rows."""
    keys: set[FillKey] = set()
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            raise HyperliquidFillIdentityError(f"{label} payload must be an object")
        key = ledger_fill_key(payload, timestamp_key=timestamp_key, label=label)
        if key in keys:
            raise HyperliquidFillIdentityError(f"duplicate {label} identity: {key}")
        keys.add(key)
    return keys


def fill_identity_gaps(
    expected: set[FillKey],
    observed: set[FillKey],
    *,
    label: str,
) -> list[str]:
    """Report missing and orphan metric identities for one fill-backed event type."""
    gaps: list[str] = []
    if expected - observed:
        gaps.append(f"{label}_missing_for_fills")
    if observed - expected:
        gaps.append(f"{label}_without_run_fill")
    return gaps
