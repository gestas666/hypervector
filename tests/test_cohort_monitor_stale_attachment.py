"""Fail-closed coverage for attaching to a slow cohort checkpoint writer."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.live.cohort_monitor_identity import (
    require_matching_checkpoint_attachment,
)


def _config(path: Path, *, profile: str, fingerprint: str) -> SimpleNamespace:
    return SimpleNamespace(
        cohort_ledger=path,
        profile_id=profile,
        profile_fingerprint=fingerprint,
        source_path=Path(f"configs/{profile}.toml"),
    )


def _write_ledger(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "event_type": "configuration_identity",
                "execution_mode": "live",
                "live_armed": True,
                "run_id": "active-run",
                "profile_id": "active-profile",
                "profile_fingerprint": "active-fingerprint",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _checkpoint(staged_fingerprint: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "multi_asset_bidirectional_live_checkpoint",
        "configuration_generation": {
            "state": "stale_runtime_configuration",
            "matches_runtime": False,
            "runtime_profile_fingerprint": "active-fingerprint",
            "current_profile_fingerprint": staged_fingerprint,
            "source_path": "configs/staged-profile.toml",
            "execution_authority": "none",
            "automatic_restart": False,
        },
        "audit": {
            "run": {
                "run_id": "active-run",
                "profile_id": "active-profile",
                "profile_fingerprint": "active-fingerprint",
            }
        },
    }


def test_stale_matching_checkpoint_is_safe_for_read_only_attachment(
    tmp_path: Path,
) -> None:
    """Age alone cannot blank an identity-proven, authority-free cockpit."""
    ledger = tmp_path / "decisions.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    active = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    staged = _config(ledger, profile="staged-profile", fingerprint="staged-fingerprint")
    checkpoint.write_text(json.dumps(_checkpoint("staged-fingerprint")))

    document = require_matching_checkpoint_attachment(checkpoint, active, staged)

    assert document["mode"] == "multi_asset_bidirectional_live_checkpoint"


def test_stale_foreign_staged_checkpoint_remains_fail_closed(tmp_path: Path) -> None:
    """A slow writer cannot masquerade as the selected staged profile."""
    ledger = tmp_path / "decisions.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    active = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    staged = _config(ledger, profile="staged-profile", fingerprint="staged-fingerprint")
    checkpoint.write_text(json.dumps(_checkpoint("foreign-fingerprint")))

    with pytest.raises(Exception, match="staged configuration identity"):
        require_matching_checkpoint_attachment(checkpoint, active, staged)
