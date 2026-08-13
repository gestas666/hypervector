"""Tests for report-only opposing-pressure maker entry timing."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from hypervector.data.oxa_archive_audit import OxaArchiveBundle
from hypervector.research.hypervelocity_pressure_pullback import (
    apply_opposed_pressure_gate,
    decision_book_pressure,
    opposed_pressure_event_decisions,
)


def test_opposed_pressure_gate_preserves_structure_and_marks_missing() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", "long", "short", None],
            "structural_direction": ["long", "long", "short", None],
        },
        index=index,
    )
    pressure = pd.Series([-0.2, 0.3, 0.4, float("nan")], index=index)

    result = apply_opposed_pressure_gate(decisions, pressure)

    assert result["entry_direction"].tolist() == ["long", None, "short", None]
    assert (
        result["structural_direction"].tolist()
        == decisions["structural_direction"].tolist()
    )
    assert result["entry_pressure_alignment"].tolist() == [
        "opposed",
        "aligned",
        "opposed",
        "missing",
    ]


def _book_row(timestamp_ms: int, bid_size: float, ask_size: float) -> dict[str, object]:
    bids = [
        {"px": str(100 - position), "sz": str(bid_size), "n": 1}
        for position in range(20)
    ]
    asks = [
        {"px": str(101 + position), "sz": str(ask_size), "n": 1}
        for position in range(20)
    ]
    return {
        "ts_exchange_ms": timestamp_ms,
        "best_bid": "100",
        "best_ask": "101",
        "bids": bids,
        "asks": asks,
    }


def test_decision_pressure_uses_latest_snapshot_before_bar_availability(
    tmp_path: Path,
) -> None:
    decision = pd.Timestamp("2026-01-01T00:00:00Z")
    available = decision + pd.Timedelta(minutes=1)
    available_ms = available.value // 1_000_000
    path = tmp_path / "books.jsonl"
    rows = [
        _book_row(available_ms - 100, 1.0, 3.0),
        _book_row(available_ms + 100, 5.0, 1.0),
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    bundle = OxaArchiveBundle(
        start=decision.to_pydatetime(),
        end=(decision + pd.Timedelta(hours=1)).to_pydatetime(),
        book_path=path,
        trade_path=None,
        book_rows=2,
        trade_rows=0,
    )
    decisions = pd.DataFrame(
        {"entry_direction": ["long"], "structural_direction": ["long"]},
        index=pd.DatetimeIndex([decision]),
    )

    observed = decision_book_pressure(decisions, (bundle,), max_age_ms=2_000)

    assert observed.iloc[0] == -0.5


def test_decision_pressure_keeps_stale_evidence_missing(tmp_path: Path) -> None:
    decision = pd.Timestamp("2026-01-01T00:00:00Z")
    available_ms = (decision + pd.Timedelta(minutes=1)).value // 1_000_000
    path = tmp_path / "books.jsonl"
    path.write_text(
        json.dumps(_book_row(available_ms - 3_000, 1.0, 3.0)) + "\n",
        encoding="utf-8",
    )
    bundle = OxaArchiveBundle(
        start=decision.to_pydatetime(),
        end=(decision + timedelta(hours=1)).to_pydatetime(),
        book_path=path,
        trade_path=None,
        book_rows=1,
        trade_rows=0,
    )
    decisions = pd.DataFrame(
        {"entry_direction": ["long"], "structural_direction": ["long"]},
        index=pd.DatetimeIndex([decision]),
    )

    observed = decision_book_pressure(decisions, (bundle,), max_age_ms=2_000)

    assert pd.isna(observed.iloc[0])


def test_pressure_event_uses_first_opposed_snapshot_inside_eligible_minute(
    tmp_path: Path,
) -> None:
    decision = pd.Timestamp("2026-01-01T00:00:00Z")
    available = decision + pd.Timedelta(minutes=1)
    available_ms = available.value // 1_000_000
    path = tmp_path / "books.jsonl"
    rows = [
        _book_row(available_ms + 1_000, 3.0, 1.0),
        _book_row(available_ms + 2_000, 1.0, 3.0),
        _book_row(available_ms + 3_000, 1.0, 5.0),
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    bundle = OxaArchiveBundle(
        start=decision.to_pydatetime(),
        end=(decision + timedelta(hours=1)).to_pydatetime(),
        book_path=path,
        trade_path=None,
        book_rows=3,
        trade_rows=0,
    )
    decisions = pd.DataFrame(
        {"entry_direction": ["long"], "structural_direction": ["long"]},
        index=pd.DatetimeIndex([decision]),
    )

    events, evidence = opposed_pressure_event_decisions(decisions, (bundle,))

    expected_event = available + pd.Timedelta(seconds=2)
    available_events = events.copy()
    available_events.index += pd.Timedelta(minutes=1)
    event_rows = available_events.loc[available_events["entry_direction"].notna()]
    assert event_rows.index.tolist() == [expected_event]
    assert event_rows.iloc[0]["entry_direction"] == "long"
    assert evidence.iloc[0]["obi_5"] == -0.5


def test_pressure_event_retains_structural_reset_without_entry(
    tmp_path: Path,
) -> None:
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    decisions = pd.DataFrame(
        {
            "entry_direction": ["long", None],
            "structural_direction": ["long", None],
        },
        index=index,
    )
    bundle = OxaArchiveBundle(
        start=index[0].to_pydatetime(),
        end=(index[0] + timedelta(hours=1)).to_pydatetime(),
        book_path=None,
        trade_path=None,
        book_rows=0,
        trade_rows=0,
    )

    events, evidence = opposed_pressure_event_decisions(decisions, (bundle,))

    assert evidence.empty
    assert events.index.tolist() == index.tolist()
    assert events["entry_direction"].isna().all()
    assert events["structural_direction"].tolist()[0] == "long"
    assert pd.isna(events["structural_direction"].tolist()[1])
