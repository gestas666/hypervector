"""Causal decision contracts for one shared BTC long/short portfolio."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from hypervector.research.maker_replay_signals import available_directions
from hypervector.research.shared_direction_portfolio import (
    build_shared_btc_decision_grid,
)
from hypervector.research.source_follow_portfolio_models import SourceSignal


_START = datetime(2026, 5, 1, tzinfo=UTC)
_END = datetime(2026, 5, 2, tzinfo=UTC)


def _long_decisions(timestamp: str) -> pd.DataFrame:
    """Build one completed-hour long pulse at its 10:59-style index."""
    return pd.DataFrame(
        {
            "entry_direction": ["long"],
            "structural_direction": ["long"],
        },
        index=pd.to_datetime([timestamp], utc=True),
    )


def test_source_short_keeps_its_exact_runtime_availability() -> None:
    """A 12:00 source decision must be actionable at 12:00, not 12:01."""
    signals = (SourceSignal("2026-05-01T12:00:00+00:00"),)

    grid = build_shared_btc_decision_grid(
        signals,
        _long_decisions("2026-05-01T10:59:00Z").iloc[0:0],
        start=_START,
        end=_END,
    )
    available = available_directions(grid.short_control)

    assert available.loc[pd.Timestamp("2026-05-01T12:00:00Z")] == "short"
    assert grid.short_events == 1
    assert grid.long_events == 0


def test_long_hour_close_gets_stop_only_when_next_hour_opens() -> None:
    """A completed 10:00 hour must create a stopped long event at 11:00."""
    grid = build_shared_btc_decision_grid(
        (),
        _long_decisions("2026-05-01T10:59:00Z"),
        start=_START,
        end=_END,
    )
    available = available_directions(grid.long_control)
    signal_row = grid.long_control.loc[pd.Timestamp("2026-05-01T10:59:00Z")]

    assert available.loc[pd.Timestamp("2026-05-01T11:00:00Z")] == "long"
    assert signal_row["entry_stop_margin_pct"] == 18.0
    assert signal_row["maximum_hold_seconds"] == 86_400.0


def test_simultaneous_signal_retains_frozen_short_control_priority() -> None:
    """An exact collision must retain short and report the dropped long event."""
    signals = (SourceSignal("2026-05-01T11:00:00+00:00"),)

    grid = build_shared_btc_decision_grid(
        signals,
        _long_decisions("2026-05-01T10:59:00Z"),
        start=_START,
        end=_END,
    )
    available = available_directions(grid.combined)
    entries = available.loc[available.notna()]

    assert entries.to_dict() == {pd.Timestamp("2026-05-01T11:00:00Z"): "short"}
    assert grid.simultaneous_long_events_dropped == 1
