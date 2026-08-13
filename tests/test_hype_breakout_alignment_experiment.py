"""Tests for the report-only HYPE entry-alignment diagnostic."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_alignment_experiment import (
    build_hype_breakout_alignment_comparison,
)


def _market() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5 * 24 * 60, freq="1min", tz="UTC")
    market = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "entry_side": None,
            "breakout_side": None,
            "state_1m": "TREND_UP",
            "state_5m": "TREND_UP",
            "context_15m": "TREND_UP",
            "structural_direction": "long",
            "funding_rate": 0.0,
        },
        index=index,
    )
    for position, entry_side, breakout_side in (
        (0, "long", "long"),
        (1_600, "long", "short"),
        (5_800, "long", "long"),
        (7_000, "long", "short"),
    ):
        market.loc[index[position], ["entry_side", "breakout_side"]] = (
            entry_side,
            breakout_side,
        )
    return market


def test_alignment_comparison_keeps_control_aligned_and_opposed_arms() -> None:
    """One post-hoc diagnostic must retain every direction cohort explicitly."""
    report = build_hype_breakout_alignment_comparison(_market(), holdout_days=1)

    assert report["schema_version"] == 2
    assert report["execution_authority"] == "none"
    assert report["contract"]["automatic_promotion"] is False
    assert report["contract"]["runtime_strategy_changed"] is False
    assert report["entry_accounting"] == {
        "raw_structural_onsets": 4,
        "breakout_side_attributable": 4,
        "aligned_onsets": 2,
        "opposed_onsets": 2,
        "unavailable_onsets": 0,
    }
    assert set(report["development"]) == {
        "control",
        "aligned_only",
        "opposed_only",
    }
    assert report["development"]["control"]["completed_trades"] == 2
    assert report["development"]["aligned_only"]["completed_trades"] == 1
    assert report["development"]["opposed_only"]["completed_trades"] == 1
    for arm in report["development"].values():
        assert arm["mean_net_return_bps_per_trade"] == pytest.approx(
            arm["net_return_bps"] / arm["completed_trades"]
        )
        assert arm["win_rate"] == pytest.approx(arm["wins"] / arm["completed_trades"])
    assert (
        "opposed_minus_aligned_mean_net_bps_per_trade"
        in report["development_comparison"]
    )


def test_alignment_comparison_rejects_untyped_breakout_sides() -> None:
    """Malformed historical direction cannot be silently treated as unavailable."""
    market = _market()
    market.loc[market.index[0], "breakout_side"] = "up"

    with pytest.raises(ValueError, match="breakout_side"):
        build_hype_breakout_alignment_comparison(market, holdout_days=1)
