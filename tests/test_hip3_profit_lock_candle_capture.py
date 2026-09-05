"""Prospective one-minute candle capture for HIP-3 profit-lock exits."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_profit_lock_candle_capture import (
    Hip3ProfitLockCandleCapture,
)
from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError


@dataclass
class _Source:
    frames: list[pd.DataFrame]
    calls: int = 0

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        assert observed_at_ms > 0
        assert timeframe == "1m"
        self.calls += 1
        return self.frames.pop(0)


def test_capture_bootstraps_then_freezes_each_new_minute_once(tmp_path: Path) -> None:
    """Only source rows first observed near their own close are prospective."""
    path = tmp_path / "profit-lock.jsonl"
    first = _frame("2026-08-18T00:00:00Z", received="2026-08-18T00:01:03Z")
    second = _frame(
        "2026-08-18T00:00:00Z",
        periods=2,
        received="2026-08-18T00:02:04Z",
    )
    source = _Source([first, second])
    capture = Hip3ProfitLockCandleCapture(source, "xyz:SP500", path)

    capture.poll(_ms("2026-08-18T00:01:02Z"))
    capture.poll(_ms("2026-08-18T00:01:30Z"))
    capture.poll(_ms("2026-08-18T00:02:02Z"))

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert source.calls == 2
    assert [row["prospective"] for row in rows] == [False, True]
    assert rows[-1]["observed_at_ms"] == _ms("2026-08-18T00:02:04Z")


def test_capture_requires_a_post_fetch_receipt_timestamp(tmp_path: Path) -> None:
    """The pre-fetch poll clock cannot masquerade as candle publication time."""
    frame = _frame("2026-08-18T00:00:00Z", received=None)
    capture = Hip3ProfitLockCandleCapture(_Source([frame]), "xyz:SP500", tmp_path / "x")

    with pytest.raises(ValueError, match="receipt timestamp"):
        capture.poll(_ms("2026-08-18T00:01:02Z"))


def test_capture_retries_when_latest_completed_minute_is_temporarily_absent(
    tmp_path: Path,
) -> None:
    """A lagging public candle response must not exhaust process restarts."""
    path = tmp_path / "profit-lock.jsonl"
    lagging = _frame("2026-08-18T00:00:00Z", received="2026-08-18T00:02:02Z")
    recovered = _frame(
        "2026-08-18T00:00:00Z",
        periods=2,
        received="2026-08-18T00:02:04Z",
    )
    capture = Hip3ProfitLockCandleCapture(
        _Source([lagging, recovered]), "xyz:SPCX", path
    )

    with pytest.raises(
        TransientCohortMarketDataError,
        match="latest_completed_minute_unavailable",
    ):
        capture.poll(_ms("2026-08-18T00:02:01Z"))

    result = capture.poll(_ms("2026-08-18T00:02:03Z"))

    assert result is not None
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["bar_close_ms"] for row in rows] == [
        _ms("2026-08-18T00:01:00Z"),
        _ms("2026-08-18T00:02:00Z"),
    ]


def _frame(start: str, *, periods: int = 1, received: str | None) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=periods, freq="1min")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 7.0,
        }
    )
    if received is not None:
        frame.attrs["received_at_ms"] = _ms(received)
    return frame


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
