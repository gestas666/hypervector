"""Controlled onset sensitivity retains chronology and unknown-state exclusions."""

from __future__ import annotations

import pandas as pd

from hypervector.research.sndk_onset_sensitivity import (
    build_sndk_onset_sensitivity_signals,
)


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-05-18", periods=101, freq="15min", tz="UTC")
    close = pd.Series([1000.0 - i for i in range(len(index))], index=index)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "decision_imbalance_10": -0.6,
            "gap_before_bars": 0,
            "end_boundary_age_ms": 1000,
            "source_snapshot_count": 2,
        },
        index=index,
    )


def test_continuing_pressure_has_one_onset_and_many_state_entries() -> None:
    """An uninterrupted trend isolates the repeated-entry mechanism."""
    result = build_sndk_onset_sensitivity_signals(_bars())
    assert result["state_entry"]["short_entry"].sum() == 47
    assert result["durable_onset"]["short_entry"].sum() == 1
    for signals in result.values():
        assert not signals["long_entry"].any()
        assert not signals["short_exit"].any()
        assert signals["stop_price"].isna().all()


def test_missing_prior_pressure_cannot_create_false_onset() -> None:
    """A stale preceding observation does not count as a known reset."""
    bars = _bars()
    bars.loc[bars.index[-2], "end_boundary_age_ms"] = 16000
    result = build_sndk_onset_sensitivity_signals(bars)
    assert result["state_entry"]["short_entry"].iloc[-1]
    assert not result["durable_onset"]["short_entry"].iloc[-1]


def test_known_pressure_reset_allows_new_onset() -> None:
    """A fresh below-threshold book is an observed false raw state."""
    bars = _bars()
    bars.loc[bars.index[-2], "decision_imbalance_10"] = 0.0
    result = build_sndk_onset_sensitivity_signals(bars)
    assert result["durable_onset"]["short_entry"].iloc[-1]


def test_future_price_changes_do_not_revise_earlier_decisions() -> None:
    """Only information available by each bar close affects its signal."""
    bars = _bars()
    expected = build_sndk_onset_sensitivity_signals(bars.iloc[:-1])
    bars.loc[bars.index[-1], ["open", "high", "low", "close"]] *= 2
    actual = build_sndk_onset_sensitivity_signals(bars)
    for name in expected:
        pd.testing.assert_frame_equal(expected[name], actual[name].iloc[:-1])
