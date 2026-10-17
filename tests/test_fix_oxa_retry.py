"""Regression: one transient 0xArchive 429/5xx must not discard a paginated fetch.

``OxaRestClient.get`` retries 429, 5xx and connection-level transport errors
with bounded, jittered backoff that honours a numeric ``Retry-After``. Other
4xx statuses and non-transport request errors still fail immediately, and no
error message ever contains the API key.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import requests

from hypervector.cli import main
from hypervector.data.oxa_api import OxaHistoryError, OxaRestClient
from hypervector.data.oxa_backfill import (
    OxaBackfillConfig,
    OxaBackfillTask,
    _execute_with_retry,
)

SECRET = "configured-secret-value"


@dataclass
class Reply:
    status_code: int = 200
    payload: object = field(default_factory=lambda: {"success": True})
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> object:
        return self.payload


class ScriptedSession:
    """Return or raise one scripted outcome per request."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def get(self, url: str, **_kwargs: object) -> Reply:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, Reply)
        return outcome


class RecordingRng:
    def __init__(self) -> None:
        self.bounds: list[tuple[float, float]] = []

    def uniform(self, low: float, high: float) -> float:
        self.bounds.append((low, high))
        return high


def _client(session: ScriptedSession, sleeps: list[float], **options: object):
    return OxaRestClient(
        api_key=SECRET,
        session=session,
        sleep=sleeps.append,
        rng=options.pop("rng", RecordingRng()),
        **options,
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_status_is_retried_then_succeeds(status: int) -> None:
    session = ScriptedSession([Reply(status), Reply(200, {"ok": 1})])
    sleeps: list[float] = []

    assert _client(session, sleeps).get("/x", params={}, timeout=1.0) == {"ok": 1}
    assert session.calls == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("boom " + SECRET),
        requests.Timeout("slow"),
        requests.exceptions.ChunkedEncodingError("cut"),
    ],
)
def test_transport_errors_are_retried(error: Exception) -> None:
    session = ScriptedSession([error, Reply(200, {"ok": 1})])
    sleeps: list[float] = []

    assert _client(session, sleeps).get("/x", params={}, timeout=1.0) == {"ok": 1}
    assert session.calls == 2


def test_exhausted_retries_raise_the_same_secret_free_error() -> None:
    session = ScriptedSession([Reply(503)] * 5)
    sleeps: list[float] = []
    rng = RecordingRng()

    with pytest.raises(OxaHistoryError) as raised:
        _client(session, sleeps, rng=rng).get("/x", params={}, timeout=1.0)

    assert str(raised.value) == "0xArchive request failed with HTTP 503"
    assert raised.value.status_code == 503
    assert session.calls == 5
    assert len(sleeps) == 4
    assert rng.bounds == [(0.0, 0.5), (0.0, 1.0), (0.0, 2.0), (0.0, 4.0)]
    assert SECRET not in str(raised.value)


def test_exhausted_transport_retries_keep_secret_free_message() -> None:
    session = ScriptedSession([requests.ConnectionError(SECRET)] * 5)

    with pytest.raises(OxaHistoryError) as raised:
        _client(session, []).get("/x", params={}, timeout=1.0)

    assert str(raised.value) == "0xArchive network request failed (ConnectionError)"
    assert raised.value.status_code is None
    assert session.calls == 5


def test_backoff_cap_bounds_late_attempts() -> None:
    session = ScriptedSession([Reply(500)] * 7 + [Reply(200, {"ok": 1})])
    rng = RecordingRng()

    _client(session, [], rng=rng, max_attempts=8).get("/x", params={}, timeout=1.0)

    assert max(high for _low, high in rng.bounds) == 8.0


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_permanent_client_errors_fail_immediately(status: int) -> None:
    session = ScriptedSession([Reply(status)])
    sleeps: list[float] = []

    with pytest.raises(OxaHistoryError, match=f"HTTP {status}") as raised:
        _client(session, sleeps).get("/x", params={}, timeout=1.0)

    assert raised.value.status_code == status
    assert session.calls == 1
    assert sleeps == []


def test_non_transport_request_errors_fail_immediately() -> None:
    session = ScriptedSession([requests.exceptions.InvalidURL("bad")])
    sleeps: list[float] = []

    with pytest.raises(OxaHistoryError, match=r"network request failed \(InvalidURL\)"):
        _client(session, sleeps).get("/x", params={}, timeout=1.0)

    assert session.calls == 1
    assert sleeps == []


@pytest.mark.parametrize(
    ("header", "expected"),
    [("3", 3.0), ("600", 60.0), ("soon", 0.5), ("-4", 0.5), ("nan", 0.5)],
)
def test_numeric_retry_after_is_honoured_and_capped(
    header: str, expected: float
) -> None:
    session = ScriptedSession(
        [Reply(429, headers={"Retry-After": header}), Reply(200, {"ok": 1})]
    )
    sleeps: list[float] = []

    _client(session, sleeps).get("/x", params={}, timeout=1.0)

    assert sleeps == [expected]


def test_responses_without_headers_attribute_remain_supported() -> None:
    @dataclass
    class Bare:
        status_code: int

        def json(self) -> object:
            return {"ok": 1}

    session = ScriptedSession([])
    replies = iter([Bare(429), Bare(200)])
    session.get = lambda url, **_kwargs: next(replies)  # type: ignore[method-assign]

    assert _client(session, []).get("/x", params={}, timeout=1.0) == {"ok": 1}


def test_invalid_json_is_not_retried_by_the_client() -> None:
    class BadJson(Reply):
        def json(self) -> object:
            raise ValueError("bad body")

    session = ScriptedSession([BadJson(200)])

    with pytest.raises(OxaHistoryError, match="invalid JSON"):
        _client(session, []).get("/x", params={}, timeout=1.0)
    assert session.calls == 1


def test_default_jitter_uses_real_random_bounds() -> None:
    session = ScriptedSession([Reply(503), Reply(200, {"ok": 1})])
    sleeps: list[float] = []

    OxaRestClient(
        api_key=SECRET, session=session, sleep=sleeps.append, rng=random.Random(1)
    ).get("/x", params={}, timeout=1.0)

    assert 0.0 <= sleeps[0] <= 0.5


def _candle_page(index: int, total: int) -> dict[str, object]:
    return {
        "success": True,
        "data": [
            {
                "timestamp": f"2026-07-26T00:{index:02d}:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 2.0,
                "quote_volume": 201.0,
                "trade_count": 3,
            }
        ],
        "meta": {
            "request_id": f"candle-{index}",
            "next_cursor": None if index == total else f"cur-{index}",
        },
    }


def test_candle_cli_survives_one_429_on_page_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pages = [Reply(200, _candle_page(index, 4)) for index in range(1, 5)]
    session = ScriptedSession(pages[:2] + [Reply(429)] + pages[2:])
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    monkeypatch.setattr("hypervector.data.oxa_api.time.sleep", lambda _delay: None)
    monkeypatch.setenv("OXA_API_KEY", SECRET)

    rc = main(
        [
            "--data-root",
            str(tmp_path),
            "archive",
            "candle-fetch",
            "--start",
            "2026-07-26T00:00:00Z",
            "--end",
            "2026-07-26T01:00:00Z",
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0, captured.err
    report = json.loads(captured.out)
    assert report["page_count"] == 4
    assert session.calls == 5
    assert SECRET not in captured.out + captured.err


def _trade_page(index: int, total: int) -> dict[str, object]:
    stamp = datetime(2026, 7, 26, tzinfo=UTC) + timedelta(seconds=index)
    base = {
        "symbol": "BTC",
        "price": "65370",
        "size": "0.1",
        "timestamp": stamp.isoformat().replace("+00:00", "Z"),
        "trade_id": 5000 + index,
    }
    return {
        "success": True,
        "data": [
            {**base, "side": "B", "crossed": False},
            {**base, "side": "A", "crossed": True},
        ],
        "meta": {
            "request_id": f"trade-{index}",
            "next_cursor": None if index == total else f"cur-{index}",
        },
    }


def test_backfill_task_retries_one_page_instead_of_the_whole_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = [Reply(200, _trade_page(index, 50)) for index in range(1, 51)]
    session = ScriptedSession(pages[:39] + [Reply(429)] + pages[39:])
    monkeypatch.setattr("hypervector.data.oxa_api.requests.Session", lambda: session)
    monkeypatch.setattr("hypervector.data.oxa_api.time.sleep", lambda _delay: None)
    monkeypatch.setattr("hypervector.data.oxa_backfill.time.sleep", lambda _delay: None)
    start = datetime(2026, 7, 26, tzinfo=UTC)
    config = OxaBackfillConfig("BTC", start, start + timedelta(hours=1), tmp_path)

    result = _execute_with_retry(
        config, OxaBackfillTask("trade", config.start, config.end), SECRET
    )

    assert result.pages == 50
    assert result.rows == 50
    assert session.calls == 51
