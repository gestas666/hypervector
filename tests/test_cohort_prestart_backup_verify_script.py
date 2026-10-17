"""Command-boundary tests for immutable cohort backup verification."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
from types import ModuleType

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupError


def _load_module() -> ModuleType:
    return import_module("hypervector.operations.cohort_prestart_backup_verify")


def test_verified_bundle_reports_non_secret_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Successful verification emits bounded operational evidence."""
    module = _load_module()
    bundle = tmp_path / "backup"
    manifest = {
        "created_at_utc": "2026-08-05T12:00:00+00:00",
        "strategy_changed": True,
        "previous_identity": {"profile_id": "old"},
        "target_identity": {"profile_id": "new"},
        "implementation_identity": {
            "algorithm": "sha256",
            "file_count": 47,
            "sha256": "implementation-sha",
        },
        "files": [{"role": "target_config"}, {"role": "cohort_ledger"}],
    }
    monkeypatch.setattr(
        module,
        "verify_cohort_prestart_backup",
        lambda path: manifest if path == bundle else {},
    )

    assert module.main(["--bundle", str(bundle)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "bundle": str(bundle),
        "created_at_utc": "2026-08-05T12:00:00+00:00",
        "file_count": 2,
        "implementation_file_count": 47,
        "implementation_sha256": "implementation-sha",
        "previous_profile_id": "old",
        "status": "verified",
        "strategy_changed": True,
        "target_profile_id": "new",
    }


def test_corrupt_bundle_returns_refusal_without_success_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A verification exception remains an explicit nonzero refusal."""
    module = _load_module()

    def fail(_path: Path) -> dict[str, object]:
        raise CohortPrestartBackupError("archive checksum mismatch")

    monkeypatch.setattr(module, "verify_cohort_prestart_backup", fail)

    assert module.main(["--bundle", str(tmp_path / "backup")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "backup verification refused: archive checksum mismatch" in captured.err
