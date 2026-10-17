"""Verified-backup boundaries for cohort profile-change approval."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import (
    ProfileChangeApprovalError,
    previous_transition_identity,
    require_approved_profile_change,
)
from hypervector.live.cohort_transition_drain import CohortTransitionDrainError
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

_V95 = Path("configs/multi_asset_growth_first_5000_review_fixes_v95.toml")
_V94 = Path("configs/multi_asset_growth_first_5000_review_actions_v94.toml")
_V95_TO_V94_ROLLBACK = Path("configs/v95-to-v94-rollback-20260927-v1.toml")


def test_previous_transition_identity_uses_hash_verified_manifest(
    tmp_path: Path,
) -> None:
    """Transition identity is returned only from the exact manifest bytes."""
    manifest = {"previous_identity": {"profile_fingerprint": "abc", "run_id": "r1"}}
    backup = _backup(tmp_path, json.dumps(manifest).encode())

    assert previous_transition_identity(backup) == ("abc", "r1")


@pytest.mark.parametrize(
    ("encoded", "expected_sha256", "message"),
    [
        (b"{}", "0" * 64, "checksum changed"),
        (b"{", None, "manifest JSON is invalid"),
        (b"[]", None, "manifest must be an object"),
    ],
)
def test_transition_identity_rejects_unverified_manifest_bytes(
    tmp_path: Path,
    encoded: bytes,
    expected_sha256: str | None,
    message: str,
) -> None:
    """Changed, malformed, and non-object manifests fail closed."""
    backup = _backup(tmp_path, encoded, expected_sha256=expected_sha256)

    with pytest.raises(CohortTransitionDrainError, match=message):
        previous_transition_identity(backup)


def test_transition_identity_rejects_missing_manifest(tmp_path: Path) -> None:
    """A missing previously verified manifest cannot authorize transition."""
    backup = _result(tmp_path / "missing.json", "0" * 64)

    with pytest.raises(CohortTransitionDrainError, match="cannot be read"):
        previous_transition_identity(backup)


def test_transition_identity_requires_profile_and_run(tmp_path: Path) -> None:
    """Both prior profile and run identities are mandatory."""
    backup = _backup(tmp_path, b'{"previous_identity": null}')

    with pytest.raises(CohortTransitionDrainError, match="prior run identity"):
        previous_transition_identity(backup)


def test_unchanged_backup_skips_change_approval(tmp_path: Path) -> None:
    """An unchanged backup does not read an approval manifest."""
    backup = replace(
        _result(tmp_path / "missing.json", "0" * 64), strategy_changed=False
    )
    config = load_multi_asset_live_config(_V95, mode="observe")

    assert require_approved_profile_change(config, backup) is None


def test_changed_backup_requires_previous_source(tmp_path: Path) -> None:
    """A changed profile cannot proceed without its prior config source."""
    manifest = {"previous_identity": {"profile_fingerprint": "abc", "run_id": "r1"}}
    backup = _backup(tmp_path, json.dumps(manifest).encode())
    config = load_multi_asset_live_config(_V95, mode="observe")

    with pytest.raises(ProfileChangeApprovalError, match="previous config source"):
        require_approved_profile_change(config, backup)


def test_changed_backup_rejects_prior_profile_drift(tmp_path: Path) -> None:
    """The prior source must reproduce the identity captured at runtime."""
    manifest = {
        "previous_identity": {
            "config_source_path": str(_V94),
            "profile_fingerprint": "0" * 64,
            "run_id": "r1",
        }
    }
    backup = _backup(tmp_path, json.dumps(manifest).encode())
    config = load_multi_asset_live_config(_V95, mode="observe")

    with pytest.raises(ProfileChangeApprovalError, match="verified backup identity"):
        require_approved_profile_change(config, backup)


def test_changed_backup_admits_real_v94_to_v95_approval(tmp_path: Path) -> None:
    """A verified V94 prior identity reaches the kept V94 -> V95 approval."""
    previous = load_multi_asset_live_config(_V94, mode="observe")
    manifest = {
        "previous_identity": {
            "config_source_path": str(_V94),
            "profile_fingerprint": previous.profile_fingerprint,
            "run_id": "r1",
        }
    }
    backup = _backup(tmp_path, json.dumps(manifest).encode())
    config = load_multi_asset_live_config(_V95, mode="observe")

    result = require_approved_profile_change(config, backup)

    assert result is not None
    assert result["state"] == "approved_profile_change"
    assert result["approval_document"] == str(config.transition_approval)
    assert result["execution_authority"] == "none"


def test_changed_backup_rejects_approval_for_another_prior_profile(
    tmp_path: Path,
) -> None:
    """A run started from the rollback twin cannot reuse the V94 -> V95 approval."""
    previous = load_multi_asset_live_config(_V95_TO_V94_ROLLBACK, mode="observe")
    manifest = {
        "previous_identity": {
            "config_source_path": str(_V95_TO_V94_ROLLBACK),
            "profile_fingerprint": previous.profile_fingerprint,
            "run_id": "r1",
        }
    }
    backup = _backup(tmp_path, json.dumps(manifest).encode())
    config = load_multi_asset_live_config(_V95, mode="observe")

    with pytest.raises(
        ProfileChangeApprovalError,
        match="previous profile fingerprint differs from approval",
    ):
        require_approved_profile_change(config, backup)


def _backup(
    root: Path,
    encoded: bytes,
    *,
    expected_sha256: str | None = None,
) -> CohortPrestartBackupResult:
    """Write a manifest fixture and return its declared backup identity."""
    path = root / "manifest.json"
    path.write_bytes(encoded)
    digest = expected_sha256 or hashlib.sha256(encoded).hexdigest()
    return _result(path, digest)


def _result(path: Path, digest: str) -> CohortPrestartBackupResult:
    """Build the minimum typed prestart result used by approval checks."""
    return CohortPrestartBackupResult(
        path=path.parent,
        manifest_path=path,
        manifest_sha256=digest,
        strategy_changed=True,
        implementation_file_count=1,
        implementation_sha256="0" * 64,
    )
