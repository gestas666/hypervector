"""Empty-window contracts for forward-only maker replay."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from hypervector.research.maker_replay import MakerReplayConfig
from hypervector.research.maker_replay_stream import (
    MakerReplayEvidenceChunk,
    replay_maker_order_chunks,
)
from hypervector.research.research_evidence_source import maker_replay_evidence


def _decisions(states: list[str]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(states), freq="1min", tz="UTC")
    return pd.DataFrame(
        {"primary_regime": states, "breakout_direction": [None] * len(states)},
        index=index,
    )


def test_empty_database_window_has_explicit_zero_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "research" / "market.duckdb"
    database_path.parent.mkdir(parents=True)
    duckdb.connect(str(database_path)).close()
    start = datetime(2026, 7, 28, tzinfo=UTC)

    evidence = maker_replay_evidence(tmp_path, "BTC", start, start, include_trades=True)

    assert tuple(evidence.chunks) == ()
    assert evidence.summary["data_source"] == "duckdb_canonical_replay"
    assert evidence.summary["hourly_windows"] == 0
    assert evidence.summary["book_snapshots"] == 0
    assert evidence.summary["public_trades"] == 0


def test_empty_trade_through_window_returns_an_empty_report() -> None:
    report = replay_maker_order_chunks(
        (),
        _decisions([]),
        MakerReplayConfig(initial_equity=100.0, fill_rule="trade-through"),
    )

    assert report.market_trade_prints == 0
    assert report.submitted_entries == 0
    assert report.final_equity == 100.0


def test_nonempty_trade_through_decisions_still_require_trade_evidence() -> None:
    with pytest.raises(ValueError, match="requires public trade prints"):
        replay_maker_order_chunks(
            (),
            _decisions(["TREND_UP"]),
            MakerReplayConfig(fill_rule="trade-through"),
        )


def _book_event(timestamp: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_ms": [int(timestamp.timestamp() * 1000)],
            "best_bid": [100.0],
            "best_ask": [101.0],
        }
    )


def test_empty_book_window_marks_execution_economics_inconclusive() -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    report = replay_maker_order_chunks(
        (
            MakerReplayEvidenceChunk(
                None, start=start, end=start + pd.Timedelta(hours=1)
            ),
        ),
        _decisions(["TREND_UP"]),
        MakerReplayConfig(fill_rule="touch"),
    )

    assert report.empty_book_evidence_windows == 1
    assert not report.execution_economics_conclusive
    assert report.first_book_gap_start_utc == start.isoformat()


def test_empty_book_window_counts_active_pending_overlap() -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    report = replay_maker_order_chunks(
        (
            MakerReplayEvidenceChunk(_book_event(start + pd.Timedelta(minutes=1))),
            MakerReplayEvidenceChunk(
                None,
                start=start + pd.Timedelta(minutes=2),
                end=start + pd.Timedelta(hours=1, minutes=2),
            ),
        ),
        _decisions(["TREND_UP", "TREND_UP"]),
        MakerReplayConfig(fill_rule="touch"),
    )

    assert report.pending_orders == 1
    assert report.active_book_gap_windows == 1


def test_complete_book_evidence_keeps_execution_economics_conclusive() -> None:
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    report = replay_maker_order_chunks(
        (MakerReplayEvidenceChunk(_book_event(start + pd.Timedelta(minutes=1))),),
        _decisions(["TREND_UP"]),
        MakerReplayConfig(fill_rule="touch"),
    )

    assert report.empty_book_evidence_windows == 0
    assert report.execution_economics_conclusive
    assert report.first_book_gap_start_utc is None
