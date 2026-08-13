from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from hypervector.research.low_tf_asset_tuning_models import (
    LowTfAssetTrial,
    TrendEntryShape,
    TrendExitShape,
    default_entry_shapes,
    default_exit_shapes,
    default_tuning_scenarios,
    default_tuning_windows,
)


def test_trial_id_is_stable_and_separates_asset_and_side() -> None:
    entry = TrendEntryShape(48, 13, 34, 20.0, 8.0)
    exit_shape = TrendExitShape(80.0, 2.0, 24)
    eth_long = LowTfAssetTrial("ETH", "long", entry, exit_shape)

    assert (
        eth_long.trial_id == LowTfAssetTrial("ETH", "long", entry, exit_shape).trial_id
    )
    assert eth_long.trial_id != replace(eth_long, side="short").trial_id
    assert eth_long.trial_id != replace(eth_long, symbol="SOL").trial_id
    assert eth_long.trial_id.startswith("lowtf-eth-long-")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((48, 34, 13, 20.0, 8.0), "ema_fast"),
        ((0, 13, 34, 20.0, 8.0), "breakout_lookback"),
        ((48, 13, 34, 101.0, 8.0), "compression_percentile"),
        ((48, 13, 34, 20.0, 0.0), "clearance_bps"),
    ],
)
def test_entry_shape_rejects_invalid_parameters(
    values: tuple[int, int, int, float, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TrendEntryShape(*values)


@pytest.mark.parametrize(
    "values",
    [
        (0.0, 2.0, 24),
        (80.0, 0.0, 24),
        (80.0, 2.0, 0),
    ],
)
def test_exit_shape_rejects_nonpositive_values(
    values: tuple[float, float, int],
) -> None:
    with pytest.raises(ValueError):
        TrendExitShape(*values)


def test_predeclared_surfaces_are_bounded_and_unique() -> None:
    entries = default_entry_shapes()
    exits = default_exit_shapes()

    assert len(entries) == 36
    assert len(set(entries)) == len(entries)
    assert len(exits) == 12
    assert len(set(exits)) == len(exits)


def test_windows_and_friction_scenarios_match_frozen_contract() -> None:
    windows = default_tuning_windows()
    scenarios = default_tuning_scenarios()

    assert tuple(window.name for window in windows) == (
        "development",
        "validation",
        "pseudo_holdout",
    )
    assert windows[0].start_utc == pd.Timestamp("2025-07-28", tz="UTC")
    assert windows[-1].end_utc == pd.Timestamp("2026-07-28", tz="UTC")
    assert [(value.name, value.round_trip_cost_bps) for value in scenarios] == [
        ("nominal", 13.0),
        ("stress", 20.0),
    ]
