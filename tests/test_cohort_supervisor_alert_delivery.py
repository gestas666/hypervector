"""Notification delivery failures remain observable without exposing endpoints."""

import json
from pathlib import Path
import subprocess
import urllib.error

import pytest

import cohort_supervisor_alerts as alerts
from cohort_supervisor_models import SupervisorPaths


def test_invalid_webhook_does_not_crash_supervision(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bad optional channel cannot remove process supervision."""
    alerts.WebhookSink("invalid-secret-endpoint").send("alert", "body", {})
    error = capsys.readouterr().err
    assert json.loads(error)["event"] == "alert_delivery_failed"
    assert "invalid-secret-endpoint" not in error


def test_notification_nonzero_exit_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Notification Centre refusal is not treated as delivered."""
    monkeypatch.setattr(
        alerts.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1)
    )
    alerts.MacNotificationSink().send("title", "body", {})
    assert json.loads(capsys.readouterr().err)["channel"] == "mac_notification"


def test_webhook_transport_failure_reports_type_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Transport errors cannot leak a configured endpoint through diagnostics."""

    def fail(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("secret-url-content")

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fail)
    alerts.WebhookSink("https://example.invalid/private").send("title", "body", {})
    error = capsys.readouterr().err
    assert json.loads(error)["channel"] == "webhook"
    assert "secret-url-content" not in error
    assert "private" not in error


def test_sinks_include_only_explicit_optional_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unconfigured external notifications create no outbound channel."""
    monkeypatch.delenv(alerts.WEBHOOK_ENV, raising=False)
    paths = SupervisorPaths(alerts=tmp_path / "alerts.jsonl")
    assert len(alerts.build_sinks(paths, notifications=False)) == 1
    monkeypatch.setenv(alerts.WEBHOOK_ENV, "https://example.invalid/topic")
    assert len(alerts.build_sinks(paths, notifications=False)) == 2
