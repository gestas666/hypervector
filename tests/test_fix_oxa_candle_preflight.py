"""Regression: candle fetches validate before spending vendor calls.

* The whole-day research-cache rule is checked before acquisition.
* A window that cannot fit in ``limit * max_pages`` fails with zero calls and
  names the page budget it needs; an omitted ``max_pages`` is derived.
* An existing complete bundle installs the research cache offline.
* A cache-install failure after acquisition still reports the stored bundle.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from hypervector.cli import main
from hypervector.cli_oxa import cmd_oxa_candle_fetch
from hypervector.data.oxa_candles import (
    OxaCandleRequest,
    acquire_and_store_candles,
    estimated_candle_pages,
)

SECRET = "never-render-this-key"
DAY = datetime(2026, 7, 1, tzinfo=UTC)


@dataclass
class Reply:
    payload: object
    status_code: int = 200

    def json(self) -> object:
        return self.payload


class MinuteSession:
    """Serve one page containing every minute of the requested window."""

    def __init__(self, minutes: int, *, start: datetime = DAY) -> None:
        self.minutes = minutes
        self.start = start
        self.calls = 0

    def get(self, url: str, **_kwargs: object) -> Reply:
        self.calls += 1
        rows = [
            {
                "timestamp": (self.start + timedelta(minutes=offset))
                .isoformat()
                .replace("+00:00", "Z"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 2.0,
                "quote_volume": 201.0,
                "trade_count": 3,
            }
            for offset in range(self.minutes)
        ]
        return Reply(
            {
                "success": True,
                "data": rows,
                "meta": {"request_id": f"candle-{self.calls}", "next_cursor": None},
            }
        )


def _cli(root: Path, *extra: str) -> int:
    return main(
        [
            "--data-root",
            str(root),
            "archive",
            "candle-fetch",
            "--start",
            DAY.isoformat(),
            *extra,
        ]
    )


def test_partial_day_cache_install_fails_before_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )

    rc = _cli(
        tmp_path,
        "--end",
        (DAY + timedelta(minutes=1439)).isoformat(),
        "--install-research-cache",
    )

    assert rc == 1
    assert calls == []
    assert "whole-day window" in capsys.readouterr().err


def test_window_beyond_page_budget_fails_with_zero_vendor_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = MinuteSession(1)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    request = OxaCandleRequest("BTC", DAY, DAY + timedelta(days=200), "1m", 10_000, 20)

    with pytest.raises(ValueError, match="needs at least 29 page") as raised:
        acquire_and_store_candles(data_root=tmp_path, api_key=SECRET, request=request)

    assert session.calls == 0
    assert "--max-pages" in str(raised.value)
    assert SECRET not in str(raised.value)


def test_page_estimate_covers_inclusive_vendor_end() -> None:
    request = OxaCandleRequest("BTC", DAY, DAY + timedelta(days=200), "1m", 10_000, 1)

    assert estimated_candle_pages(request) == 30
    exact = OxaCandleRequest("BTC", DAY, DAY + timedelta(minutes=10), "1m", 10, 1)
    assert estimated_candle_pages(exact) == 3


def test_omitted_max_pages_is_derived_from_the_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: list[OxaCandleRequest] = []
    monkeypatch.setattr(
        "hypervector.data.oxa_candles.acquire_and_store_candles",
        lambda **kwargs: captured.append(kwargs["request"]) or {"ok": True},
    )
    args = argparse.Namespace(
        data_root=tmp_path,
        symbol="BTC",
        start=DAY,
        end=DAY + timedelta(days=200),
        timeframe="1m",
        limit=10_000,
        max_pages=None,
        timeout=30.0,
        market_family="core",
        install_research_cache=False,
    )

    assert cmd_oxa_candle_fetch(args) == 0
    capsys.readouterr()
    assert captured[0].max_pages == estimated_candle_pages(captured[0]) == 30


def test_exhaustion_error_includes_page_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EndlessSession(MinuteSession):
        def get(self, url: str, **kwargs: object) -> Reply:
            reply = super().get(url, **kwargs)
            meta = reply.payload["meta"]  # type: ignore[index]
            meta["next_cursor"] = f"cur-{self.calls}"
            return reply

    session = EndlessSession(1)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    request = OxaCandleRequest("BTC", DAY, DAY + timedelta(hours=1), "1m", 10_000, 2)

    with pytest.raises(ValueError, match="max-pages exhausted") as raised:
        acquire_and_store_candles(data_root=tmp_path, api_key=SECRET, request=request)

    assert "2 page(s)" in str(raised.value)
    assert "about 2 page(s)" in str(raised.value)
    assert session.calls == 2


def test_existing_bundle_installs_research_cache_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OXA_API_KEY", SECRET)
    first = MinuteSession(1440)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: first)
    end = (DAY + timedelta(days=1)).isoformat()
    assert _cli(tmp_path, "--end", end) == 0
    capsys.readouterr()
    assert first.calls == 1

    second = MinuteSession(1440)
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: second)
    rc = _cli(tmp_path, "--end", end, "--install-research-cache")

    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert second.calls == 0
    report = json.loads(captured.out)
    assert report["reused"] is True
    assert len(pd.read_parquet(report["research_cache_path"])) == 1440
    assert SECRET not in captured.out


def test_cache_install_failure_still_reports_the_stored_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OXA_API_KEY", SECRET)
    session = MinuteSession(1435, start=DAY + timedelta(minutes=5))
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)

    rc = _cli(
        tmp_path,
        "--end",
        (DAY + timedelta(days=1)).isoformat(),
        "--install-research-cache",
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["ok"] is False
    assert "leading candle gap" in error["research_cache_error"]
    assert Path(error["acquisition"]["directory"]).is_dir()
    assert error["acquisition"]["complete"] is True
    assert SECRET not in captured.err
