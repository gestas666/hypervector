"""Shared evidence identities for immutable Hypervelocity replay reports."""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.maker_replay_context import MakerReplayContext
from hypervector.research.maker_replay_context_io import context_coverage_report


def decision_identity(decisions: pd.DataFrame) -> str:
    """Hash causal entry and structural decision values with their timestamps."""
    columns = ["entry_direction", "structural_direction"]
    columns.extend(
        name
        for name in ("entry_stop_price", "maximum_hold_seconds")
        if name in decisions
    )
    selected = decisions.loc[:, columns]
    hashed = pd.util.hash_pandas_object(
        selected.reset_index(names="decision_time_utc"), index=False
    )
    return hashlib.sha256(hashed.to_numpy(dtype="uint64").tobytes()).hexdigest()


def archive_identity(bundles: tuple[OxaArchiveBundle, ...]) -> str:
    """Hash the ordered metadata of checksum-verified archive bundles."""
    rows = [
        (
            bundle.start.isoformat(),
            bundle.end.isoformat(),
            str(bundle.book_path),
            str(bundle.trade_path),
            bundle.book_rows,
            bundle.trade_rows,
        )
        for bundle in bundles
    ]
    payload = json.dumps(rows, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def replay_archive_summary(
    bundles: tuple[OxaArchiveBundle, ...],
    context: MakerReplayContext,
) -> dict[str, object]:
    """Summarize one verified event tape and its authentic context coverage."""
    return {
        "bundle_count": len(bundles),
        "empty_book_hours": sum(bundle.book_rows == 0 for bundle in bundles),
        "empty_trade_hours": sum(bundle.trade_rows == 0 for bundle in bundles),
        "checksums_verified": True,
        "identity_sha256": archive_identity(bundles),
        "context_coverage": context_coverage_report(context),
    }
