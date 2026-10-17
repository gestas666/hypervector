"""The live REST candle poll requests only the recent window over one session."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.data.hl import bars_from_hl_payload
from hypervector.paper import live_node
from hypervector.paper.live_node import make_rest_poll_fn

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hl_candle_sample.json"
NOW = pd.Timestamp("2026-10-17T12:00:30Z")


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class _Session:
    """Fake keep-alive session that serves contiguous 1m candles."""

    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def post(self, url: str, *, json: dict, timeout: float) -> _Response:
        del url, timeout
        req = json["req"]
        self.requests.append(req)
        start = pd.Timestamp(req["startTime"], unit="ms", tz="UTC").ceil("min")
        end = pd.Timestamp(req["endTime"], unit="ms", tz="UTC")
        rows = []
        for stamp in pd.date_range(start, end.floor("min"), freq="1min"):
            ms = int(stamp.value // 1_000_000)
            rows.append(
                {"t": ms, "T": ms + 59_999, "s": req["coin"], "i": "1m",
                 "o": "100.0", "c": "100.5", "h": "101.0", "l": "99.0",
                 "v": "2.5", "n": 3}
            )
        return _Response(rows)


def test_poll_reuses_one_session_and_requests_only_the_recent_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_Session] = []

    def factory() -> _Session:
        created.append(_Session())
        return created[-1]

    monkeypatch.setattr(live_node.requests, "Session", factory)
    poll = make_rest_poll_fn("BTC", "1m", now_fn=lambda: NOW)

    first = poll(after_ts=None)
    after = pd.Timestamp("2026-10-17T11:58:00Z")
    second = poll(after_ts=after)
    third = poll(after_ts=pd.Timestamp("2026-10-15T00:00:00Z"))

    assert len(created) == 1
    session = created[0]
    spans = [
        (int(req["endTime"]) - int(req["startTime"])) / 60_000
        for req in session.requests
    ]
    assert spans[0] == pytest.approx(1440.0)  # no anchor: today's 1-day window
    assert spans[1] == pytest.approx(4.5)  # after_ts - 2 bars .. now
    assert spans[2] == pytest.approx(1440.0)  # long gap: clamped to 1 day
    assert len(first) == 1440
    assert second["timestamp"].tolist() == list(
        pd.to_datetime(["2026-10-17T11:59:00Z", "2026-10-17T12:00:00Z"], utc=True)
    )
    assert len(third) == 1440


def test_vectorized_candle_parse_matches_reference_parser() -> None:
    raw = json.loads(FIXTURE.read_text())
    malformed = list(raw) + [
        {"t": "bad", "o": "1", "h": "1", "l": "1", "c": "1"},
        {"o": "1", "h": "1", "l": "1", "c": "1"},
        {"t": raw[0]["t"] + 3_600_000, "o": "1", "h": "2", "l": "0.5", "c": "1.5"},
        {"t": raw[0]["t"] + 7_200_000, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": None},
    ]
    for payload in (raw, malformed, []):
        pd.testing.assert_frame_equal(
            live_node.candles_from_hl_payload(payload),
            bars_from_hl_payload(payload, source="hl"),
        )
