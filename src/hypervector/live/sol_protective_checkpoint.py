"""Strict checkpoint restoration and outstanding-fill verification views."""

from collections.abc import Mapping
from dataclasses import replace

from hypervector.live.hyperliquid_fill_identity import fill_trade_id
from hypervector.live.hyperliquid_protocol import SolReconciliationSnapshot
from hypervector.live.sol_protective_execution_evidence import (
    ProtectiveExecutionEvidenceError,
    ProtectiveExecutionProgress,
)

PARTIAL_PROTECTIVE_UNRESOLVED = "partial protective execution evidence remains unresolved"


def protective_progress_from_state(
    payload: Mapping[str, object],
) -> ProtectiveExecutionProgress:
    """Read legacy empty ownership explicitly; reject malformed present checkpoint data."""
    if "protective_progress" not in payload:
        return ProtectiveExecutionProgress()
    progress = ProtectiveExecutionProgress.from_payload(payload["protective_progress"])
    if not progress.stop_exit_required and any(
        fill.oid == payload.get("stop_oid") for fill in progress.fills
    ):
        raise ProtectiveExecutionEvidenceError(
            "protective checkpoint lost its stop-exit obligation"
        )
    return progress


def venue_without_credited_fills(
    venue: SolReconciliationSnapshot, progress: ProtectiveExecutionProgress
) -> SolReconciliationSnapshot:
    """Remove identical credited receipts only for outstanding-execution verification."""
    if not progress.fills:
        return venue
    credited = {fill_trade_id(fill): fill for fill in progress.fills}
    observed: set[int] = set()
    remaining = []
    for fill in venue.fills:
        identity = fill_trade_id(fill)
        if identity in observed:
            raise ProtectiveExecutionEvidenceError("duplicate receipt in protective verification")
        observed.add(identity)
        if identity in credited:
            if fill != credited[identity]:
                raise ProtectiveExecutionEvidenceError("credited protective receipt changed")
        else:
            remaining.append(fill)
    return replace(venue, fills=tuple(remaining))
