"""Fail-closed tests for archived profile-transition evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_transition_evidence import (
    require_completed_profile_transition,
)
from hypervector.live.cohort_transition_drain import (
    CohortTransitionDrain,
    CohortTransitionDrainError,
    archive_completed_transition_drain,
)
from hypervector.live.multi_asset_live_config import (
    MultiAssetLiveConfig,
    load_multi_asset_live_config,
)


def test_exact_legacy_flat_stop_archive_satisfies_transition_boundary(
    tmp_path: Path,
) -> None:
    """A preserved exact-run flat STOP can bridge a legacy stopped process."""
    previous = _source_config()
    config = _config(tmp_path)
    backup = _backup_for_previous(tmp_path, previous)
    archive = tmp_path / "data/backups/bidirectional_cohort/legacy_STOP_fixture.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(
            _legacy_payload(
                previous.symbols,
                profile_fingerprint=previous.profile_fingerprint,
            )
        ),
        encoding="utf-8",
    )

    require_completed_profile_transition(config, backup)


def test_legacy_flat_stop_archive_requires_complete_previous_symbol_set(
    tmp_path: Path,
) -> None:
    """A partial legacy boundary cannot authorize a changed-profile start."""
    previous = _source_config()
    config = _config(tmp_path)
    backup = _backup_for_previous(tmp_path, previous)
    archive = tmp_path / "data/backups/bidirectional_cohort/legacy_STOP_fixture.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(
            _legacy_payload(
                previous.symbols[:-1],
                profile_fingerprint=previous.profile_fingerprint,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(CohortTransitionDrainError, match="legacy flat-stop archive"):
        require_completed_profile_transition(config, backup)


def test_legacy_archive_validates_retired_previous_symbols(
    tmp_path: Path,
) -> None:
    """A removed asset belongs in the prior-run boundary, not the successor."""
    previous = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_nine_asset_bankroll_builder_candidate_v63.toml",
        mode="observe",
    )
    candidate = load_multi_asset_live_config(
        "configs/multi_asset_growth_first_5000_eight_asset_gold_removed_candidate_v64.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    candidate = replace(
        candidate,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )
    backup = _backup_for_previous(tmp_path, previous)
    archive = tmp_path / "data/backups/bidirectional_cohort/legacy_STOP_fixture.json"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(
            _legacy_payload(
                previous.symbols,
                profile_fingerprint=previous.profile_fingerprint,
            )
        ),
        encoding="utf-8",
    )

    require_completed_profile_transition(candidate, backup)


def test_changed_profile_still_refuses_without_transition_evidence(
    tmp_path: Path,
) -> None:
    """Approval alone cannot replace a completed flat-boundary artifact."""
    config = _config(tmp_path)

    with pytest.raises(CohortTransitionDrainError, match="completed drain archive"):
        require_completed_profile_transition(
            config, _backup(tmp_path, strategy_changed=True)
        )


def test_completed_drain_does_not_require_previous_config_source(
    tmp_path: Path,
) -> None:
    """Exact drain identity is sufficient without legacy symbol reconstruction."""
    config = _config(tmp_path)
    backup = _backup(tmp_path, strategy_changed=True)
    marker = tmp_path / "prior-transition-drain.json"
    now = datetime(2026, 8, 5, 12, tzinfo=UTC)
    control = CohortTransitionDrain(
        path=marker,
        run_id="prior-run",
        profile_fingerprint="c" * 64,
        now_fn=lambda: now,
    )
    control.activate(
        request_id="d" * 32,
        requested_at_utc="2026-08-05T11:59:59+00:00",
    )
    control.complete()
    archive_completed_transition_drain(
        path=marker,
        archive_root=(tmp_path / "data/backups/bidirectional_cohort/transition_drains"),
        expected_run_id="prior-run",
        now=now,
        confirmed=True,
    )

    require_completed_profile_transition(config, backup)


def _config(tmp_path: Path) -> MultiAssetLiveConfig:
    loaded = load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="live",
        enabled=True,
        accepts_live_risk=True,
    )
    return replace(
        loaded,
        cohort_ledger=tmp_path / "data/live/bidirectional_cohort/decisions.jsonl",
    )


def _source_config() -> MultiAssetLiveConfig:
    return load_multi_asset_live_config(
        "configs/multi_asset_bidirectional_canary.toml",
        mode="observe",
    )


def _backup(tmp_path: Path, *, strategy_changed: bool) -> CohortPrestartBackupResult:
    manifest_path = tmp_path / "backup/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = {
        "previous_identity": {
            "profile_fingerprint": "c" * 64,
            "run_id": "prior-run",
        }
    }
    encoded = json.dumps(manifest).encode()
    manifest_path.write_bytes(encoded)
    return CohortPrestartBackupResult(
        path=manifest_path.parent,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(encoded).hexdigest(),
        strategy_changed=strategy_changed,
        implementation_file_count=1,
        implementation_sha256="b" * 64,
    )


def _backup_for_previous(
    tmp_path: Path,
    previous: MultiAssetLiveConfig,
) -> CohortPrestartBackupResult:
    manifest_path = tmp_path / "backup/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = {
        "previous_identity": {
            "config_source_path": str(previous.source_path),
            "profile_fingerprint": previous.profile_fingerprint,
            "run_id": "prior-run",
        }
    }
    encoded = json.dumps(manifest).encode()
    manifest_path.write_bytes(encoded)
    return CohortPrestartBackupResult(
        path=manifest_path.parent,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(encoded).hexdigest(),
        strategy_changed=True,
        implementation_file_count=1,
        implementation_sha256="b" * 64,
    )


def _legacy_payload(
    symbols: tuple[str, ...],
    *,
    profile_fingerprint: str = "c" * 64,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reason": "legacy_flat_transition",
        "run_id": "prior-run",
        "profile_fingerprint": profile_fingerprint,
        "observed_at_utc": "2026-08-29T22:20:31+00:00",
        "symbols": list(symbols),
        "source_sequence": 466716,
    }
