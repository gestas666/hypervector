"""Construction helpers for the explicitly armed shared cohort runtime."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from hypervector.live.cohort_accounting_rollover import load_required_accounting_epoch
from hypervector.live.cohort_operator_commands import (
    CohortOperatorInbox,
    operator_command_maximum_age_seconds,
)
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrain,
    CohortTransitionDrainError,
    CohortTransitionDrainSnapshot,
    ensure_transition_drain_startable,
    load_transition_drain_snapshot,
)
from hypervector.live.multi_asset_cohort_telemetry import MultiAssetCohortTelemetry
from hypervector.live.multi_asset_live_config import (
    AssetLiveConfig,
    MultiAssetLiveConfig,
)
from hypervector.live.sol_range_onset_ledger import SolLiveLedger
from hypervector.research.cohort_live_portfolio_archive import CohortAccountingEpoch


def _accounting_epoch(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
) -> CohortAccountingEpoch | None:
    """Verify any profile-required reporting epoch before live construction."""
    bundle = getattr(args, "accounting_epoch_bundle", None)
    return load_required_accounting_epoch(bundle, config)


def _transition_recovery(
    args: argparse.Namespace,
    config: MultiAssetLiveConfig,
    path: Path,
) -> CohortTransitionDrainSnapshot | None:
    if not args.resume_transition_drain:
        ensure_transition_drain_startable(path)
        return None
    snapshot = load_transition_drain_snapshot(path)
    if snapshot.status != "active":
        raise CohortTransitionDrainError("recovery requires an active drain")
    if snapshot.profile_fingerprint != config.profile_fingerprint:
        raise CohortTransitionDrainError(
            "transition drain recovery profile identity differs"
        )
    return snapshot


def _create_transition_drain(
    path: Path,
    config: MultiAssetLiveConfig,
    run_id: str,
    recovery: CohortTransitionDrainSnapshot | None,
) -> CohortTransitionDrain:
    current_run = run_id if recovery is None else recovery.run_id
    drain = CohortTransitionDrain(
        path=path,
        run_id=current_run,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: datetime.now(UTC),
    )
    if recovery is not None:
        drain.resume_for_run(run_id)
    return drain


def _announce_backup(backup: CohortPrestartBackupResult) -> None:
    """Emit non-secret evidence that the mandatory pre-start backup passed."""
    changed = "yes" if backup.strategy_changed else "no"
    print(
        "pre-start backup verified: "
        f"path={backup.path} manifest_sha256={backup.manifest_sha256} "
        f"implementation_files={backup.implementation_file_count} "
        f"implementation_sha256={backup.implementation_sha256} "
        f"strategy_changed={changed}"
    )


def _create_operator_inbox(
    config: MultiAssetLiveConfig,
    run_id: str,
) -> CohortOperatorInbox:
    return CohortOperatorInbox(
        root=config.cohort_ledger.parent / "operator_commands",
        run_id=run_id,
        profile_fingerprint=config.profile_fingerprint,
        now_fn=lambda: datetime.now(UTC),
        maximum_age_seconds=operator_command_maximum_age_seconds(
            poll_seconds=config.poll_seconds,
            symbol_count=len(config.symbols),
        ),
    )


def _create_telemetry(
    config: MultiAssetLiveConfig,
    asset_ledgers: dict[str, SolLiveLedger],
    run_id: str,
    backup: CohortPrestartBackupResult,
    transition_drain: CohortTransitionDrain,
) -> MultiAssetCohortTelemetry:
    cohort_ledger = SolLiveLedger(
        path=config.cohort_ledger,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
    )
    return MultiAssetCohortTelemetry(
        config=config,
        ledger=cohort_ledger,
        now_fn=lambda: datetime.now(UTC),
        asset_ledgers=asset_ledgers,
        prestart_backup=backup,
        transition_drain=transition_drain,
    )


def _ledger(path: Path, config: AssetLiveConfig, run_id: str) -> SolLiveLedger:
    return SolLiveLedger(
        path=path,
        profile_id=config.profile_id,
        profile_fingerprint=config.profile_fingerprint,
        run_fingerprint=config.run_fingerprint,
        run_id=run_id,
    )
