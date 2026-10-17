"""CLI coverage for bounded 0xArchive liquidation-label acquisition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import CLI_COMMANDS, build_parser, main
from hypervector.data.oxa_liquidations import OxaLiquidationRequest


def test_liquidation_fetch_command_is_discoverable() -> None:
    """The public CLI must expose bounded liquidation acquisition."""
    assert "archive liquidation-fetch" in CLI_COMMANDS
    args = build_parser().parse_args(
        [
            "archive",
            "liquidation-fetch",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )
    assert args.command == "archive liquidation-fetch"


def test_liquidation_fetch_is_in_status_inventory() -> None:
    """Status discovery must include the liquidation acquisition command."""
    assert "archive liquidation-fetch" in CLI_COMMANDS


def _invoke_liquidation_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
) -> tuple[int, dict[str, object]]:
    captured: dict[str, object] = {}

    def fake_acquire(
        *, data_root: Path | str, api_key: str, request: OxaLiquidationRequest
    ) -> dict[str, object]:
        captured.update(data_root=data_root, api_key=api_key, request=request)
        return {
            "ok": True,
            "source": "0xarchive_hyperliquid_liquidations",
            "event_count": 3,
            "complete": False,
            "continuation_cursor": "more",
        }

    monkeypatch.setenv("OXA_API_KEY", secret)
    monkeypatch.setattr(
        "hypervector.data.oxa_liquidations.acquire_and_store_liquidations",
        fake_acquire,
        raising=False,
    )

    return main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "archive",
            "liquidation-fetch",
            "--symbol",
            "BTC",
            "--start",
            "2026-08-21T12:00:00Z",
            "--end",
            "2026-08-21T12:01:00Z",
        ]
    ), captured


def test_liquidation_fetch_cli_is_bounded_and_secret_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command must pass explicit bounds without rendering its API key."""
    secret = "configured-test-secret"
    rc, captured = _invoke_liquidation_fetch(tmp_path, monkeypatch, secret)

    output = capsys.readouterr().out
    report = json.loads(output)
    request = captured["request"]
    assert rc == 0
    assert captured["api_key"] == secret
    assert request.limit == 1000
    assert request.max_pages == 250  # a default fetch completes a window
    assert report["venue"] == "hyperliquid"
    assert secret not in output
