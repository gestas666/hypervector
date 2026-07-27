"""CLI tests for bounded 0xArchive candle acquisition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main


def test_candle_fetch_cli_reports_secret_free_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The candle command delegates explicit bounds without exposing its key."""
    secret = "never-render-this-key"
    monkeypatch.setenv("OXA_API_KEY", secret)
    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles",
        lambda **_kwargs: {
            "ok": True,
            "row_count": 1440,
            "complete": True,
            "candles_path": str(tmp_path / "candles.parquet"),
        },
    )

    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "oxa-candle-fetch",
            "--start",
            "2026-07-25T00:00:00Z",
            "--end",
            "2026-07-26T00:00:00Z",
            "--interval",
            "1m",
        ]
    )

    output = capsys.readouterr().out
    assert rc == 0
    assert json.loads(output)["row_count"] == 1440
    assert secret not in output
