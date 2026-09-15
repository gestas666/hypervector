"""Asset snapshot selection and minimal cohort ancestry for live reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from datetime import datetime
from functools import partial
from pathlib import Path

from hypervector.research.checkpoint_ledger_projection import compact_asset_ledger_rows
from hypervector.research.cohort_asset_checkpoint_recovery import (
    snapshot_current_asset_ledger,
)
from hypervector.research.cohort_live_audit_summaries import rebased
from hypervector.research.cohort_live_audit_values import (
    mapping_list,
    nonnegative_int,
    payload,
    text,
)
from hypervector.research.live_ledger_snapshot import (
    configuration_identity_ancestry,
    snapshot_decision_ledger,
    snapshot_projected_compatible_execution_ledger,
)

Record = Mapping[str, object]


def projected_asset_fill_counts(snapshot: Record) -> dict[str, int]:
    """Recover available compatible-history counts from the causal cohort snapshot."""
    counts: dict[str, int] = {}
    for asset in mapping_list(payload(snapshot).get("assets"), "snapshot assets"):
        if "fill_count" not in asset:
            continue
        symbol = text(asset.get("symbol"), "snapshot asset symbol")
        if symbol in counts:
            raise ValueError(f"duplicate snapshot asset fill count: {symbol}")
        counts[symbol] = nonnegative_int(asset.get("fill_count"), "asset fill count")
    return counts


def snapshot_checkpoint_assets(
    stack: ExitStack,
    paths: Mapping[str, Path],
    *,
    run_id: str,
    as_of: datetime,
    current_run_only: bool,
    compatible_execution_history: bool,
    projected_fill_counts: Mapping[str, int] | None = None,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    """Freeze each asset in the requested execution-history scope."""
    assets: dict[str, list[dict[str, object]]] = {}
    evidence: dict[str, dict[str, object]] = {}
    for symbol, path in paths.items():
        if current_run_only:
            snapshot = snapshot_current_asset_ledger(
                path,
                run_id=run_id,
                as_of=as_of,
                allow_incomplete_tail=True,
                minimum_fill_count=(projected_fill_counts or {}).get(symbol, 0),
            )
        elif compatible_execution_history:
            snapshot = snapshot_projected_compatible_execution_ledger(
                path,
                run_id=run_id,
                allow_incomplete_tail=True,
                stream_projector=partial(
                    compact_asset_ledger_rows, current_run_id=run_id, as_of=as_of
                ),
            )
        else:
            snapshot = snapshot_decision_ledger(path, allow_incomplete_tail=True)
        rows, facts = stack.enter_context(snapshot)
        assets[symbol] = rows
        evidence[symbol] = {"path": str(path), **facts}
    return assets, evidence


def recover_cohort_execution_identities(
    path: Path,
    cohort: list[dict[str, object]],
    evidence: dict[str, object],
    assets: Mapping[str, Sequence[Record]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Add only prior configuration rows needed to attribute recovered entries."""
    known = {text(row.get("run_id"), "cohort run") for row in cohort}
    required = {
        text(row.get("run_id"), "entry run")
        for rows in assets.values()
        for row in rows
        if row.get("event_type") == "order_acknowledgement"
        and payload(row).get("operation") == "entry"
        and payload(row).get("accepted") is True
    }.difference(known)
    if not required:
        return cohort, evidence
    offset = evidence.get("source_start_offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset <= 0:
        raise ValueError("recovered entries require a prior cohort identity prefix")
    identities, facts = configuration_identity_ancestry(
        path, frozenset(required), before_offset=offset
    )
    return list(rebased([*identities, *cohort])), {
        **evidence,
        "snapshot_scope": "current_run_with_execution_identities",
        "telemetry_scope": "current_run",
        "execution_identity_ancestry": facts,
    }
