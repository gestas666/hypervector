"""Command-boundary tests for pre-change cohort implementation snapshots."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hypervector.live.cohort_prestart_backup import CohortPrestartBackupError

SCRIPT = Path(__file__).parents[1] / "scripts/cohort_prechange_backup.py"


def _load_module() -> ModuleType:
    spec = spec_from_file_location("cohort_prechange_backup", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_uses_observe_mode_and_reports_verified_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pre-edit capture remains credential-free and emits bounded evidence."""
    module = _load_module()
    config_path = tmp_path / "active.toml"
    provider_root = tmp_path / "backtest_lab"
    bundle = tmp_path / "prestart_bundle"
    config = SimpleNamespace(profile_id="active", profile_fingerprint="abc123")
    result = SimpleNamespace(
        path=bundle,
        manifest_sha256="manifest-sha",
        strategy_changed=False,
        implementation_file_count=42,
        implementation_sha256="implementation-sha",
    )
    calls: dict[str, object] = {}

    def load(path: Path, *, mode: str) -> object:
        calls["load"] = (path, mode)
        return config

    def discover(repository: Path, provider: Path) -> dict[str, Path]:
        calls["discover"] = (repository, provider)
        return {"engine": tmp_path / "engine.py"}

    def create(value: object, *, implementation_sources: object) -> object:
        calls["create"] = (value, implementation_sources)
        return result

    monkeypatch.setattr(module, "load_multi_asset_live_config", load)
    monkeypatch.setattr(module, "discover_cohort_implementation_sources", discover)
    monkeypatch.setattr(module, "create_cohort_prestart_backup", create)
    monkeypatch.setattr(
        module,
        "verify_cohort_prestart_backup",
        lambda path: {
            "created_at_utc": "2026-08-05T16:15:00+00:00",
            "execution_authority": "none",
        }
        if path == bundle
        else {},
    )

    assert (
        module.main(
            ["--config", str(config_path), "--backtest-lab-root", str(provider_root)]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert calls["load"] == (config_path, "observe")
    assert calls["create"] == (config, {"engine": tmp_path / "engine.py"})
    assert payload == {
        "bundle": str(bundle),
        "created_at_utc": "2026-08-05T16:15:00+00:00",
        "execution_authority": "none",
        "implementation_file_count": 42,
        "implementation_sha256": "implementation-sha",
        "live_run_identity_claimed": False,
        "manifest_sha256": "manifest-sha",
        "profile_fingerprint": "abc123",
        "profile_id": "active",
        "purpose": "pre_change_implementation_baseline",
        "snapshot_mode": "observe",
        "status": "verified",
        "strategy_changed_from_latest_ledger": False,
    }


def test_snapshot_failure_is_explicit_and_has_no_success_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Archive refusal cannot be mistaken for a completed source baseline."""
    module = _load_module()
    monkeypatch.setattr(
        module,
        "load_multi_asset_live_config",
        lambda path, *, mode: SimpleNamespace(profile_id="active"),
    )
    monkeypatch.setattr(
        module,
        "discover_cohort_implementation_sources",
        lambda repository, provider: {"engine": tmp_path / "engine.py"},
    )

    def refuse(config: object, *, implementation_sources: object) -> object:
        raise CohortPrestartBackupError("source checksum changed during capture")

    monkeypatch.setattr(module, "create_cohort_prestart_backup", refuse)

    assert module.main(["--config", str(tmp_path / "active.toml")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "pre-change backup refused" in captured.err
    assert "source checksum changed during capture" in captured.err
