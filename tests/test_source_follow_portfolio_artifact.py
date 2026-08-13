"""Source-follow artifact selection for queue-aware portfolio replay."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from hypervector.research import source_follow_portfolio_artifact as artifact_io
from hypervector.research.source_follow_portfolio_artifact import (
    load_source_portfolio_selection,
)


def _artifact() -> dict[str, object]:
    """Return source evidence with both admitted and previously blocked signals."""
    outcomes = [
        {
            "decision_time_utc": "2026-04-04T02:00:00+00:00",
            "entry_eligible": True,
            "admission": "submitted",
            "side": "long",
            "confidence": 0.85,
            "signal_range_bps": 9.0,
        },
        {
            "decision_time_utc": "2026-04-04T03:00:00+00:00",
            "entry_eligible": True,
            "admission": "blocked_open_position",
            "confidence": 0.95,
            "signal_range_bps": 18.0,
        },
    ]
    return {
        "replay_window": {
            "data_start": "2026-04-04T00:00:00+00:00",
            "fresh_start": "2026-04-04T01:00:00+00:00",
            "data_end": "2026-04-05T00:00:00+00:00",
        },
        "fresh": {
            "events": 2,
            "candidates": {
                "alloc50_lev30": {
                    "event_outcomes": outcomes,
                    "replay": {"completed_trades": 1},
                }
            },
        },
    }


def test_selection_retains_signals_blocked_by_old_portfolio_path(
    tmp_path: Path,
) -> None:
    """Execution divergence must not discard source decisions skipped previously."""
    path = tmp_path / "source.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")

    selection = load_source_portfolio_selection(path, "alloc50_lev30")

    assert selection.start.isoformat() == "2026-04-04T01:00:00+00:00"
    assert selection.end.isoformat() == "2026-04-05T00:00:00+00:00"
    assert [signal.decision_time_utc for signal in selection.signals] == [
        "2026-04-04T02:00:00+00:00",
        "2026-04-04T03:00:00+00:00",
    ]
    assert [signal.direction for signal in selection.signals] == ["long", "short"]
    assert selection.baseline_replay == {"completed_trades": 1}
    assert selection.source_signal_count == 2


def test_selection_applies_explicit_minimum_signal_range(tmp_path: Path) -> None:
    """A research challenger must filter only on recorded decision-time range."""
    path = tmp_path / "source.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    selection = load_source_portfolio_selection(
        path,
        "alloc50_lev30",
        minimum_signal_range_bps=12.0,
    )

    assert selection.source_signal_count == 2
    assert len(selection.signals) == 1
    signal = selection.signals[0]
    assert signal.confidence == 0.95
    assert signal.signal_range_bps == 18.0


def test_completed_labels_select_only_frozen_live_source_contract() -> None:
    """Live selection uses causal onsets, confidence, and bounded bar range."""
    selector = getattr(artifact_io, "select_source_follow_signals", None)
    assert selector is not None
    index = pd.date_range("2026-07-30", periods=9, freq="5min", tz="UTC")
    primary = [
        "RANGE",
        "TREND_DOWN",
        "TREND_DOWN",
        "RANGE",
        "TREND_DOWN",
        "RANGE",
        "TREND_DOWN",
        "RANGE",
        "TREND_DOWN",
    ]
    labels = pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": primary,
            "secondary_code": [
                "RG",
                "TD_WEAK_CHOPPY",
                None,
                "RG",
                "TD",
                "RG",
                "TD",
                "RG",
                "TD",
            ],
            "confidence": [0.5, 0.8, 0.8, 0.5, 0.65, 0.5, 0.9, 0.5, 0.9],
        },
        index=index,
    )
    bars = pd.DataFrame(
        {
            "open": [100.0] * 9,
            "high": [100.1] * 6 + [100.04, 100.1, 100.51],
            "low": [99.9] * 6 + [99.96, 99.9, 99.49],
        },
        index=index,
    )

    signals = selector(
        labels,
        bars,
        datetime(2026, 7, 30, 0, 10, tzinfo=UTC),
        datetime(2026, 7, 30, 1, tzinfo=UTC),
    )

    assert len(signals) == 1
    assert signals[0].decision_time_utc == "2026-07-30T00:10:00+00:00"
    assert signals[0].confidence == 0.8
    assert signals[0].signal_range_bps == pytest.approx(20.0)
    assert signals[0].direction == "short"


def test_completed_labels_support_explicit_source_native_thresholds() -> None:
    """Research may remove tuned minima while retaining the frozen range ceiling."""
    index = pd.date_range("2026-07-30", periods=9, freq="5min", tz="UTC")
    labels = pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": [
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
                "RANGE",
                "TREND_DOWN",
            ],
            "secondary_code": [None] * 9,
            "confidence": [0.5, 0.8, 0.5, 0.5, 0.65, 0.5, 0.9, 0.5, 0.9],
        },
        index=index,
    )
    bars = pd.DataFrame(
        {
            "open": [100.0] * 9,
            "high": [100.1] * 6 + [100.04, 100.1, 100.51],
            "low": [99.9] * 6 + [99.96, 99.9, 99.49],
        },
        index=index,
    )

    signals = artifact_io.select_source_follow_signals(
        labels,
        bars,
        datetime(2026, 7, 30, tzinfo=UTC),
        datetime(2026, 7, 30, 1, tzinfo=UTC),
        minimum_confidence=0.0,
        minimum_signal_range_bps=0.0,
        maximum_signal_range_bps=100.0,
    )

    assert [signal.decision_time_utc for signal in signals] == [
        "2026-07-30T00:10:00+00:00",
        "2026-07-30T00:25:00+00:00",
        "2026-07-30T00:35:00+00:00",
    ]


def test_completed_label_selector_rejects_one_minute_range_bars() -> None:
    """A one-minute range must not silently impersonate the runtime 5m gate."""
    label_index = pd.date_range("2026-07-30", periods=2, freq="5min", tz="UTC")
    labels = pd.DataFrame(
        {
            "available_at": label_index + pd.Timedelta(minutes=5),
            "primary_code": ["RANGE", "TREND_DOWN"],
            "secondary_code": [None, "TD_WEAK_CHOPPY"],
            "confidence": [0.5, 0.8],
        },
        index=label_index,
    )
    minute_index = pd.date_range("2026-07-30", periods=6, freq="1min", tz="UTC")
    minute_bars = pd.DataFrame(
        {"open": 100.0, "high": 100.1, "low": 99.9},
        index=minute_index,
    )

    with pytest.raises(ValueError, match="completed five-minute bars"):
        artifact_io.select_source_follow_signals(
            labels,
            minute_bars,
            datetime(2026, 7, 30, tzinfo=UTC),
            datetime(2026, 7, 30, 1, tzinfo=UTC),
        )
