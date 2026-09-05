"""Tests for chronological BTC spot-lead orchestration."""

from __future__ import annotations

import importlib
import importlib.util

import pandas as pd
import pytest

from btc_spot_lead_catchup_fixtures import spot_lead_signal_bars


def test_btc_spot_lead_catchup_historical_module_exists() -> None:
    """The three opened partitions require one fixed orchestration path."""
    assert (
        importlib.util.find_spec(
            "hypervector.research.btc_spot_lead_catchup_historical"
        )
        is not None
    )


def test_frozen_partitions_match_preregistration() -> None:
    """Retain the exact opened development, validation, and pseudo-holdout bounds."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_historical"
    )
    assert hasattr(module, "frozen_btc_spot_lead_catchup_partitions")
    partitions = module.frozen_btc_spot_lead_catchup_partitions()
    assert [value.name for value in partitions] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert partitions[0].start_utc == pd.Timestamp("2025-07-28T00:00:00Z")
    assert partitions[-1].end_utc == pd.Timestamp("2026-07-28T00:00:00Z")


def test_historical_runner_keeps_every_scenario_and_control() -> None:
    """Publish the complete matrix even when fixture partitions are sparse."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_historical"
    )
    assert hasattr(module, "BtcSpotLeadCatchupPartition")
    assert hasattr(module, "run_btc_spot_lead_catchup_historical")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    start = perpetual.index[0]
    bounds = (
        start,
        start + pd.Timedelta(hours=58),
        start + pd.Timedelta(hours=61),
        start + pd.Timedelta(hours=64),
    )
    partitions = tuple(
        module.BtcSpotLeadCatchupPartition(name, bounds[offset], bounds[offset + 1])
        for offset, name in enumerate(("development", "validation", "pseudo_holdout"))
    )

    result = module.run_btc_spot_lead_catchup_historical(
        perpetual,
        spot,
        partitions,
    )

    assert len(result.report["summary_rows"]) == 36
    assert len(result.report["comparisons"]) == 9
    assert result.report["authority"]["execution_authority"] == "none"


def test_historical_runner_rejects_cross_venue_coverage_drift() -> None:
    """Both sources must cover the exact frozen partition boundary."""
    module = importlib.import_module(
        "hypervector.research.btc_spot_lead_catchup_historical"
    )
    assert hasattr(module, "BtcSpotLeadCatchupPartition")
    assert hasattr(module, "run_btc_spot_lead_catchup_historical")
    perpetual, spot, _, _, _ = spot_lead_signal_bars()
    start = perpetual.index[0]
    bounds = (
        start,
        start + pd.Timedelta(hours=58),
        start + pd.Timedelta(hours=61),
        start + pd.Timedelta(hours=64),
    )
    partitions = tuple(
        module.BtcSpotLeadCatchupPartition(name, bounds[offset], bounds[offset + 1])
        for offset, name in enumerate(("development", "validation", "pseudo_holdout"))
    )

    with pytest.raises(ValueError, match="spot source end is incomplete"):
        module.run_btc_spot_lead_catchup_historical(
            perpetual,
            spot.iloc[:-1],
            partitions,
        )
