"""Headless monitoring and requests preserve backend identity and no-submit behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.commands import monitor
from test_cohort_monitor_stale_attachment import _checkpoint, _config, _write_ledger


def test_monitor_publishes_the_exact_backend_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A CLI monitor projects an identity-bound source without creating a client."""
    ledger = tmp_path / "ledger.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    checkpoint.write_text(json.dumps(_checkpoint("staged-fingerprint")))
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    monkeypatch.setattr(
        monitor, "load_multi_asset_live_config", lambda *_a, **_k: config
    )
    monkeypatch.setattr(monitor, "load_required_accounting_epoch", lambda *_a: None)
    assert (
        main(
            [
                "cohort",
                "monitor",
                "--config",
                "profile.toml",
                "--source-checkpoint",
                str(checkpoint),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == _checkpoint("staged-fingerprint")


def test_monitor_rejects_a_foreign_requested_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freshness cannot substitute for the exact selected run ID."""
    ledger = tmp_path / "ledger.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    checkpoint.write_text(json.dumps(_checkpoint("staged-fingerprint")))
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    monkeypatch.setattr(
        monitor, "load_multi_asset_live_config", lambda *_a, **_k: config
    )
    monkeypatch.setattr(monitor, "load_required_accounting_epoch", lambda *_a: None)
    assert (
        main(
            [
                "cohort",
                "monitor",
                "--config",
                "profile.toml",
                "--source-checkpoint",
                str(checkpoint),
                "--run-id",
                "foreign",
            ]
        )
        == 2
    )


def test_request_default_does_not_create_an_inbox(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reviewing an operator request cannot start a transport or execution process."""
    inbox = tmp_path / "absent"
    argv = [
        "cohort",
        "request",
        "--inbox",
        str(inbox),
        "--run-id",
        "run",
        "--profile-fingerprint",
        "profile",
        "--action",
        "manual_close",
        "--symbol",
        "BTC",
    ]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not inbox.exists()
    assert main([*argv, "--submit"]) == 2
    assert not inbox.exists()


@pytest.mark.parametrize("interval", ["0", "-1", "nan", "inf"])
def test_monitor_rejects_unusable_intervals(interval: str) -> None:
    """Following cannot spin or block on an invalid polling interval."""
    assert (
        main(
            [
                "cohort",
                "monitor",
                "--config",
                "profile.toml",
                "--interval-seconds",
                interval,
            ]
        )
        == 2
    )


def test_invalid_request_settings_fail_before_publication(tmp_path: Path) -> None:
    """A settings parse error cannot publish a partially specified request."""
    settings = tmp_path / "settings.json"
    settings.write_text("broken")
    assert (
        main(
            [
                "cohort",
                "request",
                "--inbox",
                str(tmp_path),
                "--run-id",
                "run",
                "--profile-fingerprint",
                "profile",
                "--action",
                "stage_profile",
                "--symbol",
                "MULTI",
                "--settings",
                str(settings),
            ]
        )
        == 2
    )
    assert not (tmp_path / "pending").exists()


def test_following_independent_checkpoint_keeps_epoch_and_backend_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CLI forwards the proven identity/epoch and follows without ownership."""
    from types import SimpleNamespace

    ledger = tmp_path / "ledger.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    _write_ledger(ledger)
    document = _checkpoint("staged-fingerprint")
    checkpoint.write_text(json.dumps(document))
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    epoch = object()
    stop = SimpleNamespace(requested=False)
    published: list[dict[str, object]] = []
    validated: list[object] = []

    def publish(**kwargs: object) -> dict[str, object]:
        published.append(kwargs)
        return document

    def end_wait(*_args: object, **_kwargs: object) -> None:
        stop.requested = True

    monkeypatch.setattr(
        monitor, "load_multi_asset_live_config", lambda *_a, **_k: config
    )
    monkeypatch.setattr(monitor, "load_required_accounting_epoch", lambda *_a: epoch)
    monkeypatch.setattr(
        monitor,
        "require_checkpoint_accounting_epoch",
        lambda doc, observed: validated.append((doc, observed)),
    )
    monkeypatch.setattr(monitor, "publish_independent_checkpoint", publish)
    monkeypatch.setattr(monitor, "install_process_signal_stop", lambda: stop)
    monkeypatch.setattr(monitor, "stop_aware_sleep", end_wait)
    args = _monitor_args(checkpoint, "--out", str(tmp_path / "out.json"), "--follow")
    assert main(args) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2
    assert len(published) == len(validated) == 2
    assert all(
        call["run_id"] == "active-run" and call["accounting_epoch"] is epoch
        for call in published
    )


def test_monitor_refuses_missing_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing output cannot be presented as a successful monitor reading."""
    ledger = tmp_path / "ledger.jsonl"
    _write_ledger(ledger)
    config = _config(ledger, profile="active-profile", fingerprint="active-fingerprint")
    monkeypatch.setattr(
        monitor, "load_multi_asset_live_config", lambda *_a, **_k: config
    )
    monkeypatch.setattr(monitor, "load_required_accounting_epoch", lambda *_a: None)
    assert (
        main(
            [
                "cohort",
                "monitor",
                "--config",
                "profile.toml",
                "--source-checkpoint",
                str(tmp_path / "absent"),
            ]
        )
        == 2
    )


def _monitor_args(checkpoint: Path, *options: str) -> list[str]:
    return [
        "cohort",
        "monitor",
        "--config",
        "profile.toml",
        "--source-checkpoint",
        str(checkpoint),
        *options,
    ]
