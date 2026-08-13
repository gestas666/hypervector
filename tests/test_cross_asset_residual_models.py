"""Frozen contract tests for cross-asset residual research."""

from __future__ import annotations

import pytest

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
    declared_residual_pairs,
)


def test_declared_pairs_cover_each_unordered_asset_pair_once() -> None:
    """The four-asset universe must produce six stable pair identities."""
    assert declared_residual_pairs() == (
        ("BTC", "ETH"),
        ("BTC", "SOL"),
        ("BTC", "HYPE"),
        ("ETH", "SOL"),
        ("ETH", "HYPE"),
        ("SOL", "HYPE"),
    )


def test_default_contract_is_report_only_and_charges_both_legs() -> None:
    """The development screen has no execution authority and explicit costs."""
    config = CrossAssetResidualConfig()

    assert config.execution_authority == "none"
    assert config.round_trip_cost_bps_per_leg == 13.0
    assert config.fee_rate_per_side == pytest.approx(0.00045)
    assert config.slippage_bps_per_side == pytest.approx(2.0)
    assert config.gross_notional_fraction == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lookback_bars", 1),
        ("zscore_window_bars", 1),
        ("refit_interval_bars", 0),
        ("entry_z", 0.4),
        ("exit_z", 2.0),
        ("stop_z", 1.5),
        ("maximum_hold_bars", 0),
        ("leverage", 0.0),
        ("maximum_margin_fraction", 1.1),
        ("round_trip_cost_bps_per_leg", 0.0),
        ("fee_round_trip_bps_per_leg", 14.0),
    ],
)
def test_invalid_contract_values_fail_fast(field: str, value: float | int) -> None:
    """Invalid evidence semantics must not silently receive defaults."""
    with pytest.raises(ValueError):
        CrossAssetResidualConfig(**{field: value})
