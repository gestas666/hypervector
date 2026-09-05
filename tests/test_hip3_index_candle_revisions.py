"""Causal source-revision handling for exact index shadow observers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pandas as pd
import pytest

from hypervector.live.hip3_breakout_shadow_specs import (
    MU_SHADOW_SPEC,
    SP500_SHADOW_SPEC,
)
from hypervector.live.mu_hip3_breakout_shadow_runner import (
    MuHip3BreakoutShadowRunner,
    MuHip3ShadowPaths,
    MuHip3ShadowPollResult,
    _candle_contract,
    _write_status,
)
from hypervector.live.hip3_profit_lock_candle_capture import (
    profit_lock_candle_path,
)
from hypervector.paper.book import BookLevel, BookSnapshot


def test_only_index_contract_freezes_disclosed_ohlcv_revisions() -> None:
    """Index candle revisions are causal inputs; unrelated routes stay strict."""
    assert _candle_contract(SP500_SHADOW_SPEC).revision_tolerant_fields == (
        "open",
        "high",
        "low",
        "close",
        "volume",
    )
    assert _candle_contract(MU_SHADOW_SPEC).revision_tolerant_fields == ()


def test_index_status_carries_revision_disclosure_across_polls(tmp_path: Path) -> None:
    """A later clean snapshot cannot erase a detected source revision."""
    paths = _paths(tmp_path)
    changed = MuHip3ShadowPollResult(
        (),
        False,
        2,
        1,
        0,
        source_revision_rows_current_snapshot=1,
        source_revision_fields_current_snapshot=("close", "volume"),
        source_revision_bar_open_ms_current_snapshot=(900_000,),
    )
    _write_status(paths, changed, SP500_SHADOW_SPEC)
    _write_status(paths, MuHip3ShadowPollResult((), False, 3, 1, 0), SP500_SHADOW_SPEC)

    status = json.loads(paths.status.read_text(encoding="utf-8"))
    assert status["source_revision_rows_current_snapshot"] == 0
    assert status["source_revision_rows_total"] == 1
    assert status["source_revision_fields_total"] == ["close", "volume"]
    assert status["source_revision_bar_open_ms_total"] == [900_000]


def test_index_runner_reuses_first_observed_close_after_revision(
    tmp_path: Path,
) -> None:
    """Restart signal reconstruction must use the frozen decision-time close."""
    paths = _paths(tmp_path)
    first_observed = _ms("2026-08-15T10:00:03Z")
    initial = _bars(40)
    MuHip3BreakoutShadowRunner(
        source=_Source([_book(first_observed)], [initial]),
        paths=paths,
        spec=SP500_SHADOW_SPEC,
    ).poll(observed_at_ms=first_observed)
    revised = _bars(41)
    revised.loc[39, "close"] = 100.1
    next_observed = _ms("2026-08-15T10:15:03Z")
    runner = MuHip3BreakoutShadowRunner(
        source=_Source([_book(next_observed)], [revised]),
        paths=paths,
        spec=SP500_SHADOW_SPEC,
    )
    captured: dict[str, pd.DataFrame] = {}

    def capture(bars: pd.DataFrame, **_kwargs: object) -> None:
        captured["bars"] = bars
        raise _Captured

    setattr(runner, "_collector", capture)
    with pytest.raises(_Captured):
        runner.poll(observed_at_ms=next_observed)

    row = captured["bars"].loc[
        lambda value: value["timestamp"] == initial.iloc[-1]["timestamp"]
    ]
    assert row.iloc[0]["close"] == 100.0


def test_index_runner_freezes_first_observed_profit_lock_minutes(
    tmp_path: Path,
) -> None:
    """The supervised decision observer must also preserve exact exit bars."""
    paths = _paths(tmp_path)
    observed = _ms("2026-08-15T10:00:03Z")
    runner = MuHip3BreakoutShadowRunner(
        source=_Source([_book(observed)], [_bars(40)]),
        paths=paths,
        spec=SP500_SHADOW_SPEC,
    )

    runner.poll(observed_at_ms=observed)

    rows = [
        json.loads(line)
        for line in profit_lock_candle_path(paths.journal).read_text().splitlines()
    ]
    assert rows[-1]["source"] == "hyperliquid_public_candleSnapshot_1m"
    assert rows[-1]["prospective"] is False


class _Captured(Exception):
    """Stop after inspecting the runner's reconciled collector input."""


@dataclass
class _Source:
    books: list[BookSnapshot]
    frames: list[pd.DataFrame]

    def book_snapshot(self) -> BookSnapshot:
        return self.books.pop(0)

    def completed_candle_history(
        self, *, observed_at_ms: int, timeframe: str = "15m"
    ) -> pd.DataFrame:
        assert observed_at_ms >= 0
        if timeframe == "1m":
            close = pd.Timestamp(observed_at_ms, unit="ms", tz="UTC").floor("1min")
            frame = _bars(1).assign(timestamp=[close - pd.Timedelta(minutes=1)])
            frame.attrs["received_at_ms"] = observed_at_ms + 1
            return frame
        return self.frames.pop(0).copy()


def _paths(root: Path) -> MuHip3ShadowPaths:
    return MuHip3ShadowPaths(
        root / "xyz:sp500.jsonl",
        root / "unused_cohort.jsonl",
        root / "cursor.json",
        root / "journal.jsonl",
        root / "status.json",
    )


def _bars(periods: int) -> pd.DataFrame:
    timestamps = pd.date_range("2026-08-15T00:00:00Z", periods=periods, freq="15min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "volume": 7.0,
        }
    )


def _book(observed_at_ms: int) -> BookSnapshot:
    levels = tuple(BookLevel(100.0, 1.0) for _ in range(20))
    return BookSnapshot(
        symbol="xyz:SP500",
        bids=levels,
        asks=tuple(BookLevel(100.1, 1.0) for _ in range(20)),
        ts_recv_ms=float(observed_at_ms - 100),
        ts_exchange_ms=float(observed_at_ms - 200),
        source="hl_rest_l2",
    )


def _ms(value: str) -> int:
    return int(pd.Timestamp(value).timestamp() * 1_000)
