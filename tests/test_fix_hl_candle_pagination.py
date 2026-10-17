"""HL candle pagination keeps every retained candle and retries transient errors.

Regression for the empty-streak "probe jump" in ``fetch_hl_ohlcv``: after three
empty one-day chunks the cursor jumped to ``end - 5 days``, discarding 71-98% of
the 5m/15m/1h candles HL retains (it keeps the latest 5000 per interval). A
single 429/5xx also aborted the whole multi-request fetch.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

import hypervector.data.hl as hl_data

_END_MS = 1_792_195_200_000  # 2026-10-17T00:00:00Z, a 1h/15m/5m/1m boundary
_DAY_MS = 86_400_000


class _FakeResponse:
    def __init__(self, status: int, body: Any, headers: dict[str, str] | None = None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


class _FakeHyperliquid:
    """candleSnapshot with HL's retention (latest N candles) and a page cap."""

    def __init__(
        self,
        interval_ms: int,
        *,
        retained: int = 5000,
        page_cap: int = 5000,
        failures: list[_FakeResponse] | None = None,
    ) -> None:
        last_open = (_END_MS // interval_ms) * interval_ms
        self.times = [last_open - i * interval_ms for i in range(retained)][::-1]
        self.page_cap = page_cap
        self.failures = list(failures or [])
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, json: dict[str, Any], timeout: Any = None) -> _FakeResponse:
        del url, timeout
        self.requests.append(json)
        if self.failures:
            return self.failures.pop(0)
        req = json["req"]
        lo, hi = int(req["startTime"]), int(req["endTime"])
        rows = [
            {"t": t, "T": t + 1, "o": "1", "h": "2", "l": "0.5", "c": "1.5", "v": "3",
             "s": req["coin"], "i": req["interval"], "n": 1}
            for t in self.times
            if lo <= t <= hi
        ][: self.page_cap]
        return _FakeResponse(200, rows)


@pytest.fixture(autouse=True)
def _no_page_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hl_data, "_SLEEP_S", 0.0)


@pytest.mark.parametrize(
    ("timeframe", "lookback_days"),
    [("5m", 30), ("15m", 90), ("1h", 365)],
)
def test_long_lookback_keeps_every_retained_candle(timeframe: str, lookback_days: int) -> None:
    """All 5000 retained candles survive, not just the last five days."""
    interval = hl_data._INTERVAL_MS[timeframe]
    venue = _FakeHyperliquid(interval)

    frame = hl_data.fetch_hl_ohlcv(
        "BTC", timeframe, lookback_days, session=venue, end_ms=_END_MS
    )

    assert len(frame) == 5000
    assert frame["timestamp"].is_monotonic_increasing
    assert len(venue.requests) <= 3


def test_short_lookback_returns_whole_inclusive_window() -> None:
    venue = _FakeHyperliquid(60_000)

    frame = hl_data.fetch_hl_ohlcv("BTC", "1m", 1, session=venue, end_ms=_END_MS)

    # [end - 1d, end] inclusive on minute boundaries
    assert len(frame) == 1441
    assert int(frame["timestamp"].iloc[0].value // 1_000_000) == _END_MS - _DAY_MS


def test_small_response_cap_pages_forward_without_loss() -> None:
    """A venue page cap below retention is walked forward from the last candle."""
    venue = _FakeHyperliquid(900_000, page_cap=700)

    frame = hl_data.fetch_hl_ohlcv(
        "BTC", "15m", 90, session=venue, end_ms=_END_MS, sleep_fn=lambda _s: None
    )

    assert len(frame) == 5000
    assert frame["timestamp"].is_unique
    starts = [int(r["req"]["startTime"]) for r in venue.requests]
    assert starts == sorted(starts)


def test_rate_limit_is_retried_with_backoff_instead_of_aborting() -> None:
    limited = _FakeResponse(429, [], {"Retry-After": "2"})
    venue = _FakeHyperliquid(3_600_000, failures=[limited])
    delays: list[float] = []

    frame = hl_data.fetch_hl_ohlcv(
        "BTC", "1h", 365, session=venue, end_ms=_END_MS, sleep_fn=delays.append
    )

    assert len(frame) == 5000
    assert delays[0] == 2.0


def test_gateway_error_exhaustion_is_a_technical_failure() -> None:
    failures = [_FakeResponse(502, None) for _ in range(4)]
    venue = _FakeHyperliquid(60_000, failures=failures)
    delays: list[float] = []

    with pytest.raises(requests.HTTPError):
        hl_data.fetch_hl_ohlcv(
            "BTC", "1m", 1, session=venue, end_ms=_END_MS, sleep_fn=delays.append
        )

    assert delays == [1.0, 2.0, 4.0]


def test_non_list_payload_is_not_silently_treated_as_empty() -> None:
    venue = _FakeHyperliquid(60_000, failures=[_FakeResponse(200, {"error": "x"})])

    with pytest.raises(requests.exceptions.InvalidJSONError):
        hl_data.fetch_hl_ohlcv(
            "BTC", "1m", 1, session=venue, end_ms=_END_MS, sleep_fn=lambda _s: None
        )
