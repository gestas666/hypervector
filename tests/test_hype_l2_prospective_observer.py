"""Prospective, report-only HYPE L2 model journal tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from hypervector.data.hl_events import BookLevel, L2SnapshotEvent
from hypervector.data.hl_rest_l2_recorder import REST_L2_SOURCE
from hypervector.ml.hype_l2_ridge_bundle import fit_hype_l2_ridge_bundle
from hypervector.research.hype_entry_l2_features import HYPE_ENTRY_L2_FEATURES
from hypervector.research.hype_l2_prospective_observer import (
    HypeL2ProspectiveObserver,
)


def test_future_entry_is_scored_once_from_predecision_books(tmp_path: Path) -> None:
    """One future enter action produces one causal, no-authority journal row."""
    ledger = tmp_path / "hype.jsonl"
    ledger.touch()
    journal = tmp_path / "scores.jsonl"
    observer = HypeL2ProspectiveObserver(
        bundle=fit_hype_l2_ridge_bundle(_training_rows(), evidence=_evidence()),
        bundle_sha256="d" * 64,
        decision_ledger=ledger,
        cursor_path=tmp_path / "cursor.json",
        journal_path=journal,
    )
    decision_ms = 1_800_000
    for timestamp in range(decision_ms - 60_000, decision_ms, 1_000):
        observer.observe(_book(timestamp))
    _append(ledger, _decision(decision_ms, sequence=7))

    rows = observer.observe(_book(decision_ms + 1_000))

    assert len(rows) == 1
    assert rows[0]["status"] == "scored"
    assert rows[0]["execution_authority"] == "none"
    assert rows[0]["decision_time_ms"] == decision_ms
    assert rows[0]["coverage"]["books"] == 60
    assert set(rows[0]["features"]) == set(HYPE_ENTRY_L2_FEATURES)
    assert len(journal.read_text().splitlines()) == 1

    assert observer.observe(_book(decision_ms + 2_000)) == ()
    assert len(journal.read_text().splitlines()) == 1


def test_sparse_window_is_journaled_as_unscored_technical_coverage(
    tmp_path: Path,
) -> None:
    """Missing cadence must remain visible and cannot be silently imputed."""
    ledger = tmp_path / "hype.jsonl"
    ledger.touch()
    observer = HypeL2ProspectiveObserver(
        bundle=fit_hype_l2_ridge_bundle(_training_rows(), evidence=_evidence()),
        bundle_sha256="d" * 64,
        decision_ledger=ledger,
        cursor_path=tmp_path / "cursor.json",
        journal_path=tmp_path / "scores.jsonl",
    )
    decision_ms = 1_800_000
    observer.observe(_book(decision_ms - 60_000))
    observer.observe(_book(decision_ms - 1_000))
    _append(ledger, _decision(decision_ms, sequence=8))

    rows = observer.observe(_book(decision_ms + 1_000))

    assert rows[0]["status"] == "coverage_unavailable"
    assert "features" not in rows[0]
    assert "snapshot_count" in rows[0]["reason"]


def _training_rows(count: int = 40) -> pd.DataFrame:
    index = np.arange(count, dtype=float)
    return pd.DataFrame(
        {
            **{
                name: np.sin(index / (position + 2.0))
                for position, name in enumerate(HYPE_ENTRY_L2_FEATURES)
            },
            "gross_return_bps": index - 20.0,
            "signal_time_utc": pd.date_range(
                "2026-01-01", periods=count, freq="5min", tz="UTC"
            ),
        }
    )


def _evidence() -> dict[str, str]:
    return {
        "feature_artifact_sha256": "a" * 64,
        "model_plan_sha256": "b" * 64,
        "development_report_sha256": "c" * 64,
    }


def _book(timestamp_ms: int) -> L2SnapshotEvent:
    midpoint = 50.0 + timestamp_ms / 10_000_000.0
    bids = tuple(BookLevel(midpoint - 0.01 * (i + 1), 10.0 - i, 1) for i in range(5))
    asks = tuple(BookLevel(midpoint + 0.01 * (i + 1), 3.0 + i, 1) for i in range(5))
    return L2SnapshotEvent(
        "HYPE",
        timestamp_ms,
        timestamp_ms * 1_000_000,
        bids,
        asks,
        source=REST_L2_SOURCE,
    )


def _decision(timestamp_ms: int, *, sequence: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_type": "regime_decision",
        "run_id": "future-run",
        "sequence": sequence,
        "observed_at_utc": "2026-08-06T05:00:01+00:00",
        "payload": {
            "routing_action": "enter",
            "decision_time_ms": timestamp_ms,
            "side": "long",
            "symbol": "HYPE",
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
        },
    }


def _append(path: Path, payload: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
