"""Funding and L2 info reads retry 429/5xx; the book recorder survives one bad poll.

Regression: ``_request_hl_funding_page`` had no retry at all, ``_request_hl_l2_book``
retried only 429 (a 502 raised immediately), and ``run_book_recorder`` exited on
the first transient error while building a new Session for every snapshot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import requests

import hypervector.data.book_record as book_record
from hypervector.data.hl import fetch_hl_funding_history, fetch_hl_l2_book
from hypervector.paper.book import BookLevel, BookSnapshot


def _response(status: int, body: Any = None, headers: dict[str, str] | None = None) -> requests.Response:
    import json as _json

    response = requests.Response()
    response.status_code = status
    response.url = "https://example.invalid/info"
    response._content = _json.dumps(body).encode()
    response.headers.update(headers or {})
    return response


class _Session:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def post(self, url: str, json: dict[str, Any], timeout: Any = None) -> requests.Response:
        del url, json, timeout
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


_FUNDING_ROW = {"coin": "BTC", "fundingRate": "0.00001", "premium": "0", "time": 1_784_988_000_030}


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_funding_page_retries_transient_http_status(status: int) -> None:
    session = _Session([_response(status), _response(200, [_FUNDING_ROW])])
    delays: list[float] = []

    frame = fetch_hl_funding_history(
        "BTC",
        start_time=pd.Timestamp("2026-07-25T14:00:00Z"),
        end_time=pd.Timestamp("2026-07-25T14:00:00Z"),
        session=session,  # type: ignore[arg-type]
        sleep_fn=delays.append,
    )

    assert session.calls == 2
    assert delays == [1.0]
    assert len(frame) == 1


def test_funding_retry_exhaustion_keeps_http_error_contract() -> None:
    session = _Session([_response(503) for _ in range(4)])
    delays: list[float] = []

    with pytest.raises(requests.HTTPError):
        fetch_hl_funding_history(
            "BTC",
            start_time=pd.Timestamp("2026-07-25T12:00:00Z"),
            end_time=pd.Timestamp("2026-07-25T15:00:00Z"),
            session=session,  # type: ignore[arg-type]
            sleep_fn=delays.append,
        )

    assert delays == [1.0, 2.0, 4.0]


_L2 = {
    "coin": "BTC",
    "time": 1_700_000_000_000,
    "levels": [
        [{"px": "100.0", "sz": "1.0", "n": 1}],
        [{"px": "100.1", "sz": "2.0", "n": 1}],
    ],
}


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_l2_book_retries_gateway_errors(status: int) -> None:
    session = _Session([_response(status), _response(200, _L2)])
    delays: list[float] = []

    snap = fetch_hl_l2_book("BTC", session=session, sleep_fn=delays.append)  # type: ignore[arg-type]

    assert session.calls == 2
    assert delays == [1.0]
    assert snap.best_bid() == 100.0


def test_l2_book_permanent_error_is_not_retried() -> None:
    session = _Session([_response(400)])
    delays: list[float] = []

    with pytest.raises(RuntimeError, match="HL l2Book fetch failed"):
        fetch_hl_l2_book("BTC", session=session, sleep_fn=delays.append)  # type: ignore[arg-type]

    assert session.calls == 1
    assert delays == []


def _snapshot(symbol: str = "BTC") -> BookSnapshot:
    return BookSnapshot(
        symbol=symbol,
        bids=(BookLevel(100.0, 1.0),),
        asks=(BookLevel(101.0, 1.0),),
        ts_recv_ms=1_784_992_000_050.0,
        ts_exchange_ms=1_784_992_000_000.0,
        source="hl_rest_l2",
    )


def test_recorder_counts_a_transient_failure_and_keeps_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions: list[object] = []
    outcomes: list[Any] = [_snapshot(), RuntimeError("HL l2Book fetch failed: 502"), _snapshot()]

    def fake_fetch(symbol: str, *, session: object = None, **_kw: Any) -> BookSnapshot:
        del symbol
        sessions.append(session)
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(book_record, "fetch_hl_l2_book", fake_fetch)
    monkeypatch.setattr(book_record.time, "sleep", lambda _s: None)

    result = book_record.run_book_recorder(
        tmp_path, symbol="BTC", interval_secs=0.0, max_snapshots=2
    )

    assert result["snapshots"] == 2
    assert result["errors"] == 1
    assert "502" in str(result["last_error"])
    # One persistent session is reused for every poll.
    assert len(sessions) == 3
    assert sessions[0] is not None
    assert all(s is sessions[0] for s in sessions)


def test_recorder_stops_after_bounded_consecutive_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def always_fail(symbol: str, **_kw: Any) -> BookSnapshot:
        raise RuntimeError(f"HL l2Book fetch failed for {symbol}: 503")

    monkeypatch.setattr(book_record, "fetch_hl_l2_book", always_fail)
    monkeypatch.setattr(book_record.time, "sleep", lambda _s: None)

    with pytest.raises(RuntimeError, match="consecutive"):
        book_record.run_book_recorder(
            tmp_path,
            symbol="BTC",
            interval_secs=0.0,
            max_snapshots=5,
            max_consecutive_errors=3,
        )
