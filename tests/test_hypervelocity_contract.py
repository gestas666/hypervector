"""Contract tests for the faithful Hypervelocity baseline."""

from __future__ import annotations

import pytest

from hypervector.regime.models import BreakoutDirection, PrimaryRegime
from hypervector.strategies.hypervelocity_contract import (
    HypervelocityContract,
    entry_direction_for,
    faithful_regime_config,
)


def test_primary_regime_vocabulary_is_canonical() -> None:
    assert {regime.value for regime in PrimaryRegime} == {
        "TREND_UP",
        "TREND_DOWN",
        "BREAKOUT",
        "RANGE",
        "TRANSITION",
        "UNKNOWN",
    }


@pytest.mark.parametrize(
    ("primary", "breakout", "expected"),
    [
        (PrimaryRegime.TREND_UP, None, "long"),
        (PrimaryRegime.TREND_DOWN, None, "short"),
        (PrimaryRegime.BREAKOUT, BreakoutDirection.UPWARD, "long"),
        (PrimaryRegime.BREAKOUT, BreakoutDirection.DOWNWARD, "short"),
        (PrimaryRegime.BREAKOUT, None, None),
        (PrimaryRegime.RANGE, None, None),
        (PrimaryRegime.TRANSITION, None, None),
        (PrimaryRegime.UNKNOWN, None, None),
    ],
)
def test_entry_direction_matches_observed_strategy_states(
    primary: PrimaryRegime,
    breakout: BreakoutDirection | None,
    expected: str | None,
) -> None:
    assert entry_direction_for(primary, breakout) == expected


def test_fixed_contract_converts_equity_and_margin_target() -> None:
    contract = HypervelocityContract()

    allocation = contract.allocate(equity=100.0)

    assert allocation.margin == pytest.approx(70.0)
    assert allocation.notional == pytest.approx(2_800.0)
    assert contract.target_price_fraction == pytest.approx(0.002)
    assert contract.margin_fraction == pytest.approx(0.70)
    assert contract.leverage == pytest.approx(40.0)
    assert contract.target_margin_pct == pytest.approx(8.0)
    assert contract.order_type == "limit"
    assert contract.time_in_force == "post_only"


def test_faithful_regime_config_matches_zero_false_range_training_candidate() -> None:
    config = faithful_regime_config()

    assert (config.ema_fast, config.ema_slow) == (5, 13)
    assert config.minimum_trend_gap_bps == pytest.approx(0.5)
    assert config.breakout_clearance_bps == pytest.approx(8.0)
    assert config.breakout_volume_multiple == pytest.approx(2.5)


@pytest.mark.parametrize("equity", [0.0, -1.0])
def test_allocation_rejects_non_positive_equity(equity: float) -> None:
    with pytest.raises(ValueError, match="equity must be positive"):
        HypervelocityContract().allocate(equity)


def test_contract_rejects_mutating_fixed_baseline() -> None:
    with pytest.raises(ValueError, match="margin_fraction must be 0.70"):
        HypervelocityContract(margin_fraction=0.50)
