"""Accounting-epoch validation at the cohort checkpoint worker boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import sys

from hypervector.research.cohort_background_sync import ResearchSyncError
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch
from hypervector.research.cohort_rolling_checkpoint import validated_portfolio_archive

SyncFn = Callable[[Path, Path], Mapping[str, object]]


def bind_sync_to_accounting_epoch(
    sync_fn: SyncFn,
    epoch: CohortAccountingEpoch | None,
) -> SyncFn:
    """Require an exact epoch archive from each isolated research sync."""

    def sync(database: Path, ledger_root: Path) -> Mapping[str, object]:
        result = sync_fn(database, ledger_root)
        archive = validated_epoch_archive(result, epoch)
        if epoch is not None and archive is None:
            raise ResearchSyncError("accounting epoch archive is missing")
        return result

    return sync


def accounting_epoch_worker_args(epoch: CohortAccountingEpoch) -> list[str]:
    """Serialize one exact epoch for the isolated DuckDB worker."""
    return [
        "--accounting-epoch-id",
        epoch.epoch_id,
        "--accounting-epoch-profile-fingerprint",
        epoch.profile_fingerprint,
        "--accounting-epoch-start-ms",
        str(epoch.start_venue_timestamp_ms),
    ]


def research_worker_command(
    worker: Path,
    database: Path,
    ledger_root: Path,
    cached_checkpoint: Path | None,
    accounting_epoch: CohortAccountingEpoch | None,
) -> list[str]:
    """Build one exact isolated research-import worker command."""
    command = [
        sys.executable,
        str(worker),
        "--database",
        str(database),
        "--ledger-root",
        str(ledger_root),
    ]
    if cached_checkpoint is not None:
        command.extend(["--cached-checkpoint", str(cached_checkpoint)])
    if accounting_epoch is not None:
        command.extend(accounting_epoch_worker_args(accounting_epoch))
    return command


def validated_epoch_archive(
    result: Mapping[str, object],
    epoch: CohortAccountingEpoch | None = None,
) -> Mapping[str, object] | None:
    """Validate an optional archive and its exact reporting boundary."""
    archive = result.get("portfolio_archive")
    if archive is None:
        return None
    try:
        validated = validated_portfolio_archive(archive)
    except ValueError as exc:
        raise ResearchSyncError(str(exc)) from exc
    expected = None if epoch is None else epoch.to_dict()
    if validated.get("accounting_epoch") != expected:
        raise ResearchSyncError("research worker accounting epoch differs")
    return validated
