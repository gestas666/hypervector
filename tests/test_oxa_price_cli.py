"""CLI coverage for bounded 0xArchive mark/oracle price acquisition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hypervector.cli import build_parser, main
from hypervector.data.oxa_prices import OxaPriceRequest


def test_price_fetch_command_is_discoverable() -> None:
    """The public CLI must expose the bounded price acquisition command."""
    parser = build_parser()
    choices: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            choices.update(action.choices)

    assert "oxa-price-fetch" in choices


def test_price_fetch_cli_is_bounded_and_secret_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command passes explicit bounds without rendering its API key."""
    captured: dict[str, object] = {}
    secret = "configured-test-secret"

    def fake_acquire(
        *, data_root: Path | str, api_key: str, request: OxaPriceRequest
    ) -> dict[str, object]:
        captured.update(data_root=data_root, api_key=api_key, request=request)
        return {
            "ok": True,
            "prices_path": str(tmp_path / "prices.parquet"),
            "row_count": 1,
            "complete": True,
        }

    monkeypatch.setenv("OXA_API_KEY", secret)
    monkeypatch.setattr(
        "hypervector.data.oxa_prices.acquire_and_store_prices", fake_acquire
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "oxa-price-fetch",
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
    assert request.max_pages == 1
    assert report["venue"] == "hyperliquid"
    assert secret not in output
