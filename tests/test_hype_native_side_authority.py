"""Directional authority comparison tests for the HYPE-native candidate."""

from __future__ import annotations

import pandas as pd

from hypervector.research.hype_native_side_authority import (
    build_hype_native_side_authority_comparison,
)


def _market() -> pd.DataFrame:
    """Build three causal days with recurring long and short native onsets."""
    index = pd.date_range("2026-01-01", periods=3 * 1_440, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "state_5m": "BREAKOUT",
            "state_1m": "RANGE",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    for position in range(0, len(frame), 240):
        frame.iloc[position, frame.columns.get_loc("entry_side")] = "long"
        frame.iloc[position + 60, frame.columns.get_loc("entry_side")] = "short"
        frame.iloc[position + 120, frame.columns.get_loc("entry_side")] = "short"
    return frame


def test_side_authority_preserves_opposite_onset_exit_without_short_entry() -> None:
    """Long-only replay treats native short onsets as exits rather than entries."""
    report = build_hype_native_side_authority_comparison(_market(), holdout_days=1)

    long_only = report["development"]["long_only"]
    bidirectional = report["development"]["bidirectional"]
    assert long_only["side_counts"] == {"long": long_only["completed_trades"]}
    assert bidirectional["side_counts"]["short"] > 0
    assert long_only["exit_reasons"]["opposite_strategy_intent"] > 0
    assert report["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False


def test_side_authority_reports_winner_sensitivity_for_every_arm() -> None:
    """Every directional arm exposes its dependence on one large winner."""
    report = build_hype_native_side_authority_comparison(_market(), holdout_days=1)

    for partition in ("development", "holdout_already_opened"):
        for arm in ("bidirectional", "long_only", "short_only"):
            values = report[partition][arm]
            assert "net_excluding_largest_winner_bps" in values
            assert sum(values["side_counts"].values()) == values["completed_trades"]
