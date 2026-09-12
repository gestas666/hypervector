"""Recover inherited asset execution history for bounded cohort checkpoints."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path

from hypervector.live.sol_range_onset_live_journal import build_live_journal
from hypervector.research.checkpoint_ledger_projection import compact_asset_ledger_rows
from hypervector.research.cohort_live_audit_history import select_asset_evidence
from hypervector.research.cohort_live_audit_summaries import rebased
from hypervector.research.cohort_live_audit_values import (
    mapping_list,
    number,
    payload,
    positive_int,
    text,
    timestamp,
)
from hypervector.research.live_ledger_snapshot import (
    snapshot_current_run_ledger,
    snapshot_projected_compatible_execution_ledger,
)

Record = Mapping[str, object]


@dataclass
class _Dependencies:
    reasons: set[str] = field(default_factory=set)
    entry_oids: set[int] = field(default_factory=set)
    closed_oids: set[int] = field(default_factory=set)


@contextmanager
def snapshot_current_asset_ledger(
    path: Path,
    *,
    run_id: str,
    as_of: datetime,
    allow_incomplete_tail: bool = False,
) -> Iterator[tuple[list[dict[str, object]], dict[str, object]]]:
    """Keep the current run unless its accounting depends on prior execution."""
    with snapshot_current_run_ledger(
        path, run_id=run_id, allow_incomplete_tail=allow_incomplete_tail
    ) as (rows, evidence):
        dependencies = _execution_dependencies(rows, run_id, as_of)
        if not dependencies.reasons:
            yield rows, evidence
            return
    with snapshot_projected_compatible_execution_ledger(
        path,
        run_id=run_id,
        allow_incomplete_tail=allow_incomplete_tail,
        stream_projector=partial(
            compact_asset_ledger_rows, current_run_id=run_id, as_of=as_of
        ),
    ) as (rows, evidence):
        _validate_inherited_execution(rows, run_id, as_of, dependencies)
        evidence.update(
            requested_snapshot_scope="current_run",
            history_recovery_reasons=sorted(dependencies.reasons),
            inherited_entry_oids=sorted(dependencies.entry_oids),
            inherited_closed_oids=sorted(dependencies.closed_oids),
        )
        yield rows, evidence


def _execution_dependencies(
    rows: Sequence[Record], run_id: str, as_of: datetime
) -> _Dependencies:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("asset recovery cutoff must be timezone-aware")
    dependencies = _Dependencies()
    entries: set[int] = set()
    for row in rows:
        if row.get("run_id") != run_id or timestamp(row) > as_of:
            continue
        values = payload(row)
        event = row.get("event_type")
        if event == "order_acknowledgement" and values.get("operation") == "entry":
            if values.get("accepted") is True:
                entries.add(positive_int(values.get("oid"), "entry oid"))
        if event == "state_transition" and values.get("entry_oid") is not None:
            oid = positive_int(values.get("entry_oid"), "owned entry oid")
            if oid not in entries:
                dependencies.entry_oids.add(oid)
                dependencies.reasons.add("entry_owned_before_current_run")
        if not entries:
            _add_preentry_dependency(row, dependencies)
    return dependencies


def _add_preentry_dependency(row: Record, dependencies: _Dependencies) -> None:
    event = row.get("event_type")
    values = payload(row)
    if event in {"fill", "funding", "close"}:
        dependencies.reasons.add(f"{event}_before_current_entry")
    if event == "close" and values.get("verified_flat") is True:
        dependencies.closed_oids.add(positive_int(values.get("oid"), "closed oid"))
    if event == "position" and number(values.get("size_signed"), "position size"):
        dependencies.reasons.add("position_before_current_entry")
    size = values.get("position_size_signed")
    if event == "state_transition" and size is not None and number(size, "owned size"):
        dependencies.reasons.add("position_before_current_entry")


def _validate_inherited_execution(
    rows: Sequence[Record],
    run_id: str,
    as_of: datetime,
    dependencies: _Dependencies,
) -> None:
    identity = next(
        row
        for row in rows
        if row.get("run_id") == run_id
        and row.get("event_type") == "configuration_identity"
    )
    symbol = text(payload(identity).get("symbol"), "asset symbol")
    _, history = select_asset_evidence({symbol: rows}, (symbol,), run_id, as_of=as_of)
    journal = build_live_journal(rebased(history[symbol]))
    closed = mapping_list(journal.get("trades"), "closed lifecycles")
    active = mapping_list(journal.get("open_lifecycles"), "open lifecycles")
    entries = {row.get("entry_oid") for row in [*closed, *active]}
    missing = dependencies.entry_oids.difference(entries)
    if missing:
        raise ValueError(
            f"{symbol} inherited entry missing from compatible execution history: {sorted(missing)}"
        )
    missing_closes = dependencies.closed_oids.difference(
        row.get("exit_oid") for row in closed
    )
    if missing_closes:
        raise ValueError(
            f"{symbol} inherited close missing from compatible execution history: {sorted(missing_closes)}"
        )
