from __future__ import annotations

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from hypervector.research.cross_asset_impulse_models import (
    CrossAssetImpulseConfig,
    declared_impulse_folds,
    declared_impulse_pairs,
    declared_impulse_variants,
)


def test_declared_pairs_preserve_the_frozen_leader_hierarchy() -> None:
    assert declared_impulse_pairs() == (
        ("BTC", "ETH"),
        ("BTC", "SOL"),
        ("BTC", "HYPE"),
        ("ETH", "SOL"),
        ("ETH", "HYPE"),
    )


def test_default_contract_freezes_clock_horizons_and_authority() -> None:
    config = CrossAssetImpulseConfig()

    assert config.lookback_minutes == 10_080
    assert config.minimum_valid_returns == 9_980
    assert config.warmup_start == pd.Timestamp("2025-07-20T23:55:00Z")
    assert config.impulse_return_minutes == 5
    assert config.horizons_minutes == (5, 15, 30)
    assert config.cooldown_minutes == 30
    assert config.execution_authority == "none"
    assert config.nominal_round_trip_cost_bps == 13.0
    assert config.stress_round_trip_cost_bps == 20.0
    assert config.delayed_entry_minutes == 1
    assert config.placebo_lag_minutes == 1_440
    assert config.minimum_direction_events_per_fold == 10
    assert config.report_only is True
    assert declared_impulse_variants() == (
        "primary",
        "leader_only_ablation",
        "follower_only_momentum",
        "lagged_leader_placebo",
    )

    with pytest.raises(FrozenInstanceError):
        config.cooldown_minutes = 15  # type: ignore[misc]


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"lookback_minutes": 4}, "lookback_minutes"),
        ({"minimum_valid_returns": 10_081}, "minimum_valid_returns"),
        ({"impulse_return_minutes": 0}, "impulse_return_minutes"),
        ({"leader_z_threshold": 0.0}, "leader_z_threshold"),
        ({"catchup_gap_threshold": -0.1}, "catchup_gap_threshold"),
        ({"cooldown_minutes": 29}, "longest horizon"),
        ({"horizons_minutes": (15, 5)}, "strictly increasing"),
        ({"nominal_round_trip_cost_bps": 0.0}, "cost"),
        ({"stress_round_trip_cost_bps": 12.0}, "stress"),
        ({"placebo_lag_minutes": 0}, "placebo"),
    ],
)
def test_invalid_contract_values_fail_explicitly(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CrossAssetImpulseConfig(**updates)  # type: ignore[arg-type]


def test_contract_window_is_timezone_aware_and_half_open() -> None:
    config = CrossAssetImpulseConfig()

    assert config.development_start == pd.Timestamp("2025-07-28T00:00:00Z")
    assert config.development_end == pd.Timestamp("2026-01-28T00:00:00Z")
    assert declared_impulse_folds(config) == (
        (
            "fold_1",
            pd.Timestamp("2025-07-28T00:00:00Z"),
            pd.Timestamp("2025-09-28T00:00:00Z"),
        ),
        (
            "fold_2",
            pd.Timestamp("2025-09-28T00:00:00Z"),
            pd.Timestamp("2025-11-28T00:00:00Z"),
        ),
        (
            "fold_3",
            pd.Timestamp("2025-11-28T00:00:00Z"),
            pd.Timestamp("2026-01-28T00:00:00Z"),
        ),
    )


def test_naive_or_reversed_windows_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CrossAssetImpulseConfig(development_start=pd.Timestamp("2025-07-28T00:00:00"))
    with pytest.raises(ValueError, match="precede"):
        CrossAssetImpulseConfig(
            development_start=pd.Timestamp("2026-01-28T00:00:00Z"),
            development_end=pd.Timestamp("2025-07-28T00:00:00Z"),
        )
