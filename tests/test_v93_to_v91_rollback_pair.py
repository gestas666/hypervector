"""The pre-authored V93 -> V91 rollback passes live startup's approval gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupResult
from hypervector.live.cohort_profile_change_approval import (
    require_approved_profile_change,
    validate_profile_change_approval,
)
from hypervector.live.cohort_runtime_preflight import validate_runtime_configuration
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config

import cohort_rollback_profile as rollback

V91 = "configs/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml"
V93 = "configs/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml"
ROLLBACK = "configs/v93-to-v91-rollback-20260924-v1.toml"
APPROVAL = "docs/live-approvals/v93-to-v91-rollback-20260924-v1.json"
V93_FINGERPRINT = "33131f1898d86dda4f5cab2b6091748144f6a81da29b9c9464a644b330dc3e05"
ROLLBACK_FINGERPRINT = (
    "db497d40e71fd1c1830bb2daf20b9b05ded20d1c3ee00e2ff252fabd4430ab63"
)
OPERATOR_APPROVAL = (
    "yes the private page then plan and execute options 1 through 4 "
    "im approving it now completely"
)


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_rollback_pair_identity_is_pinned() -> None:
    current = load_multi_asset_live_config(V93, mode="observe")
    target = load_multi_asset_live_config(V91, mode="observe")
    candidate = load_multi_asset_live_config(ROLLBACK, mode="observe")
    document = json.loads(Path(APPROVAL).read_text())

    assert current.profile_fingerprint == V93_FINGERPRINT
    assert candidate.profile_fingerprint == ROLLBACK_FINGERPRINT
    assert candidate.profile_id == target.profile_id
    assert candidate.transition_approval == Path(APPROVAL)
    assert document["operator_approval"] == OPERATOR_APPROVAL
    assert document["change_scopes"] == [f"rollback_to_{target.profile_id}"]
    assert document["previous_profile"]["profile_fingerprint"] == V93_FINGERPRINT
    assert document["candidate_profile"]["profile_fingerprint"] == (
        ROLLBACK_FINGERPRINT
    )
    assert document["rollback"] == {
        "config_path": f"../../{V93}",
        "profile_fingerprint": V93_FINGERPRINT,
        "sha256": _sha256(V93),
    }


def test_live_startup_and_preflight_accept_the_rollback(tmp_path: Path) -> None:
    current = load_multi_asset_live_config(V93, mode="observe")
    candidate = load_multi_asset_live_config(
        ROLLBACK, mode="live", enabled=True, accepts_live_risk=True
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "previous_identity": {
                    "profile_id": current.profile_id,
                    "profile_fingerprint": current.profile_fingerprint,
                    "run_id": "bidirectional-live-1790196314874",
                    "config_source_path": V93,
                }
            }
        )
    )
    backup = CohortPrestartBackupResult(
        path=tmp_path,
        manifest_path=manifest,
        manifest_sha256=_sha256(manifest),
        strategy_changed=True,
        implementation_file_count=1,
        implementation_sha256="0" * 64,
    )

    validate_runtime_configuration(candidate)
    startup = require_approved_profile_change(candidate, backup)
    preflight = validate_profile_change_approval(
        current, candidate, candidate.transition_approval
    )

    assert startup == preflight
    assert startup is not None and startup["state"] == "approved_profile_change"
    assert startup["retired_execution_scopes"] == []


def test_rollback_tool_verify_mode_accepts_the_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repository)

    assert (
        rollback.main(
            ["--root", str(repository), "--current", V93, "--verify", ROLLBACK]
        )
        == 0
    )
