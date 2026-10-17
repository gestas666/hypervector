"""CLI coverage for bounded 0xArchive public-trade acquisition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hypervector.cli import CLI_COMMANDS, build_parser, main
from hypervector.data.oxa_trades import DEFAULT_TRADE_MAX_PAGES, OxaTradeRequest


def test_trade_fetch_command_is_discoverable() -> None:
    """The public CLI must expose the bounded trade acquisition command."""
    assert "archive trade-fetch" in CLI_COMMANDS
    args = build_parser().parse_args(
        [
            "archive",
            "trade-fetch",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )
    assert args.command == "archive trade-fetch"


def test_trade_fetch_limit_help_is_concise_and_range_is_validated() -> None:
    """The bounded limit must not expand 1,000 choices into CLI help."""
    parser = build_parser()
    groups = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    archive = groups.choices["archive"]
    actions = next(
        action
        for action in archive._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    trade_parser = actions.choices["trade-fetch"]

    assert "--limit LIMIT" in trade_parser.format_help()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "archive",
                "trade-fetch",
                "--start",
                "2026-07-26T23:50:00Z",
                "--end",
                "2026-07-26T23:51:00Z",
                "--limit",
                "1001",
            ]
        )


def test_trade_fetch_cli_is_bounded_and_secret_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command passes explicit bounds and never renders its API key."""
    captured: dict[str, object] = {}
    secret = "configured-test-secret"

    def fake_acquire(
        *, data_root: Path | str, api_key: str, request: OxaTradeRequest
    ) -> dict[str, object]:
        captured.update(data_root=data_root, api_key=api_key, request=request)
        return {
            "ok": True,
            "trades_path": str(tmp_path / "trades.jsonl"),
            "trade_count": 1,
            "complete": False,
            "continuation_cursor": "more",
        }

    monkeypatch.setenv("OXA_API_KEY", secret)
    monkeypatch.setattr(
        "hypervector.data.oxa_trades.acquire_and_store_trades", fake_acquire
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "archive",
            "trade-fetch",
            "--symbol",
            "BTC",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(output)
    request = captured["request"]
    assert rc == 0
    assert captured["api_key"] == secret
    assert request.limit == 1000
    assert request.max_pages == DEFAULT_TRADE_MAX_PAGES
    assert report["venue"] == "hyperliquid"
    assert secret not in output


def test_trade_fetch_cli_returns_non_success_on_vendor_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Technical failure cannot return a success-shaped trade path."""
    from hypervector.data.oxa_api import OxaHistoryError

    def fail_acquire(
        *, data_root: Path | str, api_key: str, request: OxaTradeRequest
    ) -> dict[str, object]:
        raise OxaHistoryError("0xArchive request failed with HTTP 503")

    monkeypatch.setenv("OXA_API_KEY", "configured-test-secret")
    monkeypatch.setattr(
        "hypervector.data.oxa_trades.acquire_and_store_trades", fail_acquire
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "archive",
            "trade-fetch",
            "--start",
            "2026-07-26T23:50:00Z",
            "--end",
            "2026-07-26T23:51:00Z",
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(captured.err)
    assert rc == 1
    assert captured.out == ""
    assert report["ok"] is False
    assert "trades_path" not in report
