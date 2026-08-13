"""Frozen contract tests for cross-sectional breadth research."""

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
    CrossAssetBreadthEvent,
    declared_breadth_folds,
    declared_breadth_variants,
)


def test_default_contract_matches_preregistered_breadth_plan() -> None:
    config = CrossAssetBreadthConfig()

    assert config.symbols == ("BTC", "ETH", "SOL", "HYPE")
    assert config.return_bars == 6
    assert config.lookback_bars == 672
    assert config.minimum_valid_bars == 666
    assert config.breadth_required == 3
    assert config.dispersion_quantile == pytest.approx(0.75)
    assert config.cooldown_minutes == 60
    assert config.horizon_minutes == 60
    assert config.delayed_entry_minutes == 1
    assert config.placebo_lag_bars == 96
    assert config.nominal_round_trip_cost_bps == pytest.approx(13.0)
    assert config.stress_round_trip_cost_bps == pytest.approx(20.0)
    assert config.report_only is True
    assert config.execution_authority == "none"
    assert declared_breadth_variants() == (
        "primary",
        "btc_only_momentum",
        "lagged_breadth_placebo",
    )


def test_default_folds_are_fixed_chronological_windows() -> None:
    folds = declared_breadth_folds(CrossAssetBreadthConfig())

    assert folds == (
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("return_bars", 0),
        ("lookback_bars", 5),
        ("minimum_valid_bars", 673),
        ("breadth_required", 2),
        ("dispersion_quantile", 1.0),
        ("cooldown_minutes", 59),
        ("horizon_minutes", 0),
        ("delayed_entry_minutes", 0),
        ("placebo_lag_bars", 0),
        ("nominal_round_trip_cost_bps", 0.0),
        ("stress_round_trip_cost_bps", 12.0),
    ],
)
def test_contract_rejects_nonfrozen_or_incoherent_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        CrossAssetBreadthConfig(**{field: value})


def test_event_is_immutable_and_has_no_execution_authority() -> None:
    event = CrossAssetBreadthEvent(
        bar_open_at="2025-08-01T00:00:00+00:00",
        decision_time_utc="2025-08-01T00:15:00+00:00",
        entry_time_utc="2025-08-01T00:15:00+00:00",
        signal_variant="primary",
        direction="long",
        btc_normalized_return=2.0,
        breadth_count=4,
        dispersion=1.2,
        dispersion_threshold=1.0,
        valid_symbols=4,
    )

    assert event.report_only is True
    assert event.execution_authority == "none"
    with pytest.raises(FrozenInstanceError):
        event.direction = "short"  # type: ignore[misc]
