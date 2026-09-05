"""Accept exact drain or legacy-flat evidence for a profile transition."""

from __future__ import annotations

from pathlib import Path

from hypervector.live.cohort_legacy_flat_stop import (
    LegacyFlatStopError,
    load_legacy_flat_stop_archive,
    verify_legacy_flat_stop_archive,
)
from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import (
    previous_profile_config,
    previous_transition_identity,
)
from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrainError,
    load_transition_drain_snapshot,
    verify_completed_transition_drain_archive,
)
from hypervector.live.multi_asset_live_config import MultiAssetLiveConfig


def require_completed_profile_transition(
    config: MultiAssetLiveConfig,
    backup: CohortPrestartBackupResult,
) -> None:
    """Require exactly one prior-run flat-boundary archive before a change."""
    if not backup.strategy_changed:
        return
    prior_profile, prior_run = previous_transition_identity(backup)
    drain_matches, legacy_matches = _required_archive_matches(
        config, prior_profile, prior_run
    )
    previous = previous_profile_config(config, backup) if legacy_matches else None
    if previous is not None and previous.profile_fingerprint != prior_profile:
        raise CohortTransitionDrainError("previous profile identity differs")
    _validated_archive_evidence(
        prior_profile,
        prior_run,
        drain_matches,
        legacy_matches,
        previous=previous,
    )


def validate_profile_transition_archive(
    config: MultiAssetLiveConfig,
    previous: MultiAssetLiveConfig,
    prior_run: str,
) -> dict[str, object]:
    """Validate and describe the one exact prior-run flat-boundary archive."""
    prior_profile = previous.profile_fingerprint
    drain_matches, legacy_matches = _required_archive_matches(
        config, prior_profile, prior_run
    )
    return _validated_archive_evidence(
        prior_profile,
        prior_run,
        drain_matches,
        legacy_matches,
        previous=previous,
    )


def _required_archive_matches(
    config: MultiAssetLiveConfig,
    prior_profile: str,
    prior_run: str,
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    root = _archive_root(config)
    drain_matches = _matching_drain_archives(root, prior_profile, prior_run)
    legacy_matches = _matching_legacy_archives(root, prior_profile, prior_run)
    matches = (*drain_matches, *legacy_matches)
    if len(matches) != 1:
        raise CohortTransitionDrainError(
            "changed profile requires exactly one completed drain archive or "
            "validated legacy flat-stop archive for prior run "
            f"{prior_run}; found {len(matches)}"
        )
    return drain_matches, legacy_matches


def _validated_archive_evidence(
    prior_profile: str,
    prior_run: str,
    drain_matches: tuple[Path, ...],
    legacy_matches: tuple[Path, ...],
    *,
    previous: MultiAssetLiveConfig | None,
) -> dict[str, object]:
    if legacy_matches:
        if previous is None:
            raise CohortTransitionDrainError(
                "legacy flat-stop archive requires previous profile config"
            )
        _verify_legacy_archive(legacy_matches[0], previous, prior_run)
        archive = legacy_matches[0]
        state = "validated_legacy_flat_stop_archive"
    else:
        verify_completed_transition_drain_archive(
            drain_matches[0],
            expected_run_id=prior_run,
            expected_profile_fingerprint=prior_profile,
        )
        archive = drain_matches[0]
        state = "validated_completed_transition_drain_archive"
    return {
        "state": state,
        "archive_path": str(archive),
        "prior_run_id": prior_run,
        "prior_profile_fingerprint": prior_profile,
        "execution_authority": "none",
        "automatic_order_action": False,
    }


def _verify_legacy_archive(
    path: Path,
    previous: MultiAssetLiveConfig,
    prior_run: str,
) -> None:
    try:
        verify_legacy_flat_stop_archive(
            path,
            expected_profile_fingerprint=previous.profile_fingerprint,
            expected_run_id=prior_run,
            expected_symbols=previous.symbols,
        )
    except LegacyFlatStopError as exc:
        raise CohortTransitionDrainError(str(exc)) from exc


def _matching_drain_archives(
    root: Path, prior_profile: str, prior_run: str
) -> tuple[Path, ...]:
    matches: list[Path] = []
    paths = sorted((root / "transition_drains").glob("transition_drain_*.json"))
    for path in paths:
        snapshot = load_transition_drain_snapshot(path)
        if (
            snapshot.status == "completed"
            and snapshot.profile_fingerprint == prior_profile
            and snapshot.run_id == prior_run
        ):
            matches.append(path)
    return tuple(matches)


def _matching_legacy_archives(
    root: Path, prior_profile: str, prior_run: str
) -> tuple[Path, ...]:
    matches: list[Path] = []
    try:
        for path in sorted(root.glob("legacy_STOP_*")):
            evidence = load_legacy_flat_stop_archive(path)
            if (
                evidence.profile_fingerprint == prior_profile
                and evidence.run_id == prior_run
            ):
                matches.append(path)
    except LegacyFlatStopError as exc:
        raise CohortTransitionDrainError(str(exc)) from exc
    return tuple(matches)


def _archive_root(config: MultiAssetLiveConfig) -> Path:
    live_root = config.cohort_ledger.parent
    data_root = live_root.parents[1]
    return data_root / "backups" / live_root.name
