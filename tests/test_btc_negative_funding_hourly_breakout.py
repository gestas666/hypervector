from __future__ import annotations

import importlib

import pandas as pd
import pytest

from btc_negative_funding_breakout_fixtures import (
    negative_funding_breakout_bars,
)


def test_frozen_config_rejects_execution_authority_and_parameter_drift() -> None:
    """Keep the candidate report-only and prevent outcome-driven retuning."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_hourly_breakout"
    )
    with pytest.raises(ValueError, match="report-only"):
        module.BtcNegativeFundingBreakoutConfig(execution_authority="live")
    with pytest.raises(ValueError, match="frozen"):
        module.BtcNegativeFundingBreakoutConfig(prior_high_hours=24)


def test_negative_funding_filters_an_otherwise_identical_breakout() -> None:
    """Emit the primary only when the strictly prior funding observation is negative."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_hourly_breakout"
    )
    bars, funding, positive_time, negative_time = negative_funding_breakout_bars()
    result = module.build_btc_negative_funding_breakout_signals(bars, funding)
    primary = result.candidate_entries.index[result.candidate_entries["long_entry"]]
    control = result.control_entries.index[result.control_entries["long_entry"]]
    assert list(primary) == [negative_time]
    assert list(control) == [positive_time, negative_time]
    assert result.candidate_entries["short_entry"].sum() == 0


def test_funding_at_decision_boundary_is_not_used_early() -> None:
    """Exclude a funding settlement timestamped exactly at the hour boundary."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_hourly_breakout"
    )
    bars, funding, _, negative_time = negative_funding_breakout_bars()
    boundary = negative_time + pd.Timedelta(minutes=1)
    funding.loc[boundary - pd.Timedelta(hours=1)] = 0.00001
    funding.loc[boundary] = -0.00001
    result = module.build_btc_negative_funding_breakout_signals(bars, funding)
    assert not bool(result.candidate_entries.loc[negative_time, "long_entry"])
    diagnostic = result.completed_hourly.loc[negative_time.floor("h")]
    assert diagnostic["latest_prior_funding_rate"] == pytest.approx(0.00001)


def test_gap_marker_resets_hourly_warmup_and_breakout_state() -> None:
    """Do not carry EMA, prior-high, or onset state across explicit missing evidence."""
    module = importlib.import_module(
        "hypervector.research.btc_negative_funding_hourly_breakout"
    )
    bars, funding, _, _ = negative_funding_breakout_bars()
    bars["gap_before_bars"] = 0
    bars.iloc[60 * 60, bars.columns.get_loc("gap_before_bars")] = 2
    result = module.build_btc_negative_funding_breakout_signals(bars, funding)
    assert result.candidate_entries["long_entry"].sum() == 0
    assert result.control_entries["long_entry"].sum() == 0
