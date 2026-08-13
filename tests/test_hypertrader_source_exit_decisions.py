"""Causal decision contracts for source-regime exit research."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hypertrader_exit_decisions import (
    selective_recipe_source_exit_decisions,
)
from hypervector.research.maker_replay_signals import (
    available_directions,
    available_structural_directions,
)


def test_source_exit_decisions_hold_range_and_publish_confirmed_opposite() -> None:
    index = pd.date_range("2026-07-27T00:00:00Z", periods=4, freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": ["RANGE", "TREND_DOWN", "RANGE", "TREND_UP"],
            "secondary_code": [None] * 4,
        },
        index=index,
    )
    events = pd.DataFrame(
        [
            {
                "recipe_id": "follow_td_all_day",
                "label_time_utc": index[1],
                "decision_time_utc": index[2],
                "side": "short",
                "maximum_hold_seconds": 86_400.0,
            }
        ]
    )

    decisions = selective_recipe_source_exit_decisions(events, labels)
    entries = available_directions(decisions)
    structure = available_structural_directions(decisions)

    assert entries.loc[pd.Timestamp("2026-07-27T00:10:00Z")] == "short"
    assert structure.loc[pd.Timestamp("2026-07-27T00:10:00Z")] == "short"
    assert structure.loc[pd.Timestamp("2026-07-27T00:15:00Z")] is None
    assert structure.loc[pd.Timestamp("2026-07-27T00:20:00Z")] == "long"


def test_source_exit_decisions_map_upward_breakout_as_opposite() -> None:
    index = pd.date_range("2026-07-27T00:00:00Z", periods=2, freq="5min")
    labels = pd.DataFrame(
        {
            "primary_code": ["TREND_DOWN", "BREAKOUT"],
            "secondary_code": [None, "BK_UPWARD"],
        },
        index=index,
    )
    events = pd.DataFrame(
        columns=[
            "recipe_id",
            "label_time_utc",
            "decision_time_utc",
            "side",
            "maximum_hold_seconds",
        ]
    )

    decisions = selective_recipe_source_exit_decisions(events, labels)
    structure = available_structural_directions(decisions)

    assert structure.iloc[-1] == "long"
