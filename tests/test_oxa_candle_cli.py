"""CLI tests for bounded 0xArchive candle acquisition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypervector.cli import main
from hypervector.data.oxa_candles import OxaCandleRequest


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


@pytest.mark.parametrize(
    ("symbol", "options", "family"),
    [("BTC", [], "core"), ("xyz:SNDK", ["--market-family", "hip3"], "hip3")],
)
def test_candle_cli_passes_explicit_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    symbol: str,
    options: list[str],
    family: str,
) -> None:
    """CLI family selection reaches the request without symbol rewriting."""
    requests: list[OxaCandleRequest] = []

    def acquire(
        *, data_root: Path, api_key: str, request: OxaCandleRequest
    ) -> dict[str, object]:
        requests.append(request)
        return {"ok": True}

    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles", acquire
    )
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "oxa-candle-fetch",
            "--symbol",
            symbol,
            "--start",
            "2026-07-01T14:00:00Z",
            "--end",
            "2026-07-01T15:00:00Z",
            *options,
        ]
    )
    capsys.readouterr()
    assert rc == 0
    assert len(requests) == 1
    assert requests[0].symbol == symbol
    assert requests[0].market_family == family


@pytest.mark.parametrize(("symbol", "family"), [("xyz:SNDK", "core"), ("SNDK", "hip3")])
def test_candle_cli_rejects_family_mismatch_before_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    symbol: str,
    family: str,
) -> None:
    """Invalid identity fails locally before a remote request is possible."""

    def unexpected(**_kwargs: object) -> dict[str, object]:
        pytest.fail("acquisition was called for an invalid symbol")

    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles", unexpected
    )
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "oxa-candle-fetch",
            "--symbol",
            symbol,
            "--market-family",
            family,
            "--start",
            "2026-07-01T14:00:00Z",
            "--end",
            "2026-07-01T15:00:00Z",
        ]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False


@pytest.mark.parametrize("interval", ["5m", "15m", "1h"])
def test_nonminute_cache_install_fails_before_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    interval: str,
) -> None:
    """Minute gap repair cannot silently populate a different interval cache."""
    calls: list[object] = []

    def acquire(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles", acquire
    )
    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "oxa-candle-fetch",
            "--start",
            "2026-07-01T00:00:00Z",
            "--end",
            "2026-07-02T00:00:00Z",
            "--interval",
            interval,
            "--install-research-cache",
        ]
    )
    assert rc == 1
    assert calls == []
    assert "requires --interval 1m" in capsys.readouterr().err
