"""Current-run and compatible-history selection for cohort live audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from hypervector.research.cohort_live_audit_values import (
    event_rows,
    is_armed_live,
    payload,
    text,
    timestamp,
)

Record = Mapping[str, object]
AssetRows = dict[str, tuple[Record, ...]]


def select_asset_evidence(
    ledgers: Mapping[str, Sequence[Record]],
    symbols: tuple[str, ...],
    run_id: str,
    *,
    as_of: datetime,
) -> tuple[AssetRows, AssetRows]:
    """Separate current-process health rows from compatible execution history."""
    if set(ledgers) != set(symbols):
        raise ValueError("asset ledgers must exactly cover configured symbols")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("asset evidence cutoff must be timezone-aware")
    current: AssetRows = {}
    history: AssetRows = {}
    for symbol in symbols:
        rows = _validated_records(ledgers[symbol], f"{symbol} asset")
        bounded = tuple(row for row in rows if timestamp(row) <= as_of)
        selected = tuple(row for row in bounded if row.get("run_id") == run_id)
        identity = _current_identity(selected, symbol, run_id)
        current[symbol] = selected
        history[symbol] = tuple(
            row for row in bounded if _matches_execution_identity(row, identity)
        )
    return current, history


def select_all_time_asset_evidence(
    ledgers: Mapping[str, Sequence[Record]],
    symbols: tuple[str, ...],
    run_id: str,
    *,
    as_of: datetime,
) -> AssetRows:
    """Select every armed-live asset row observed by the audit cutoff."""
    if set(ledgers) != set(symbols):
        raise ValueError("asset ledgers must exactly cover configured symbols")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("all-time asset evidence cutoff must be timezone-aware")
    output: AssetRows = {}
    for symbol in symbols:
        rows = _validated_records(ledgers[symbol], f"{symbol} asset")
        output[symbol] = tuple(
            row for row in rows if is_armed_live(row) and timestamp(row) <= as_of
        )
    return output


def _validated_records(
    records: Sequence[Record],
    label: str,
) -> tuple[Record, ...]:
    if not records:
        raise ValueError(f"{label} live audit requires at least one record")
    rows = tuple(records)
    for expected, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} ledger row {expected} must be an object")
        if row.get("sequence") != expected:
            raise ValueError(
                f"{label} ledger sequence must be contiguous at {expected}"
            )
        payload(row)
    return rows


def _current_identity(
    selected: tuple[Record, ...],
    symbol: str,
    run_id: str,
) -> Record:
    if not selected or not all(is_armed_live(row) for row in selected):
        raise ValueError(f"{symbol} lacks armed live evidence for run {run_id}")
    identities = event_rows(selected, "configuration_identity")
    if len(identities) != 1 or payload(identities[0]).get("symbol") != symbol:
        raise ValueError(f"{symbol} asset configuration identity is invalid")
    return identities[0]


def _matches_execution_identity(row: Record, identity: Record) -> bool:
    return is_armed_live(row) and all(
        row.get(key) == text(identity.get(key), key)
        for key in ("profile_id", "profile_fingerprint", "run_fingerprint")
    )
