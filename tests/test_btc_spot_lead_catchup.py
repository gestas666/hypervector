"""Tests for the preregistered BTC cross-venue spot-lead signals."""

from __future__ import annotations

import importlib
import importlib.util

import pandas as pd
import pytest

from btc_spot_lead_catchup_fixtures import spot_lead_signal_bars


def test_btc_spot_lead_catchup_module_exists() -> None:
    """The preregistered signal family must have an isolated module."""
    assert (
        importlib.util.find_spec("hypervector.research.btc_spot_lead_catchup")
        is not None
    )


def test_frozen_config_rejects_authority_and_parameter_drift() -> None:
    """Keep the cross-venue experiment outcome-blind and immutable."""
    module = importlib.import_module("hypervector.research.btc_spot_lead_catchup")
    assert hasattr(module, "BtcSpotLeadCatchupConfig")
    with pytest.raises(ValueError, match="report-only"):
        module.BtcSpotLeadCatchupConfig(execution_authority="live")
    with pytest.raises(ValueError, match="frozen"):
        module.BtcSpotLeadCatchupConfig(prior_high_bars=24)


def test_primary_native_control_and_lag_placebo_are_distinct() -> None:
    """Emit each preregistered arm only from its exact completed-bar condition."""
    module = importlib.import_module("hypervector.research.btc_spot_lead_catchup")
    assert hasattr(module, "build_btc_spot_lead_catchup_signals")
    perpetual, spot, candidate_time, placebo_time, native_time = spot_lead_signal_bars()

    result = module.build_btc_spot_lead_catchup_signals(perpetual, spot)

    candidate = result.candidate_entries.index[result.candidate_entries["long_entry"]]
    placebo = result.placebo_entries.index[result.placebo_entries["long_entry"]]
    native = result.native_control_entries.index[
        result.native_control_entries["long_entry"]
    ]
    assert list(candidate) == [candidate_time]
    assert list(placebo) == [placebo_time]
    assert list(native) == [native_time]
    diagnostic = result.completed_15m.loc[candidate_time.floor("15min")]
    assert bool(diagnostic["spot_breakout"])
    assert bool(diagnostic["perpetual_lag"])
    assert bool(diagnostic["perpetual_participation"])
    assert bool(diagnostic["hourly_trend_up"])
    assert result.candidate_entries["short_entry"].sum() == 0


def test_cross_venue_minute_indexes_must_match_exactly() -> None:
    """Never nearest-neighbor join asynchronous spot and perpetual minutes."""
    module = importlib.import_module("hypervector.research.btc_spot_lead_catchup")
    assert hasattr(module, "build_btc_spot_lead_catchup_signals")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()

    with pytest.raises(ValueError, match="identical UTC minute indexes"):
        module.build_btc_spot_lead_catchup_signals(perpetual, spot.iloc[:-1])


def test_gap_in_either_venue_resets_joint_warmup() -> None:
    """Do not carry trends, highs, or onset state across one source's gap."""
    module = importlib.import_module("hypervector.research.btc_spot_lead_catchup")
    assert hasattr(module, "build_btc_spot_lead_catchup_signals")
    perpetual, spot, candidate_time, _, _ = spot_lead_signal_bars()
    spot.loc[candidate_time.floor("h") - pd.Timedelta(hours=20), "gap_before_bars"] = 2

    result = module.build_btc_spot_lead_catchup_signals(perpetual, spot)

    assert result.candidate_entries["long_entry"].sum() == 0
    assert result.placebo_entries["long_entry"].sum() == 0
    assert result.native_control_entries["long_entry"].sum() == 0
