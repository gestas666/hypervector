"""Scaled-account friction contracts for the HIP-3 oil mechanism."""

from __future__ import annotations

from importlib import import_module

import pytest


def _fee_profile(symbol: str = "xyz:BRENTOIL") -> dict[str, object]:
    return {
        "symbol": symbol,
        "fees": {"effective_taker_rate": 0.0000864},
    }


def _liquidity_profile(symbol: str = "xyz:BRENTOIL") -> dict[str, object]:
    return {
        "symbol": symbol,
        "spread_bps": {"p90": 3.75, "p99": 13.31},
        "notionals": [
            {
                "notional_usd": 750.0,
                "both_complete_rate": 1.0,
                "round_trip_visible_cost_bps": {
                    "p90": 4.20,
                    "p99": 15.64,
                },
            }
        ],
    }


def test_scaled_friction_uses_depth_increment_without_double_counting_spread() -> None:
    """Normalized replay size maps to $5K size and adds only depth over BBO."""
    module = import_module("hypervector.research.hip3_oil_shock_reversion_friction")

    contract = module.build_hip3_oil_friction_contract(
        symbol="xyz:BRENTOIL",
        venue_max_leverage=20.0,
        fee_profile=_fee_profile(),
        liquidity_profile=_liquidity_profile(),
    )

    assert contract.scaled_notional_usd == 750.0
    assert contract.nominal_depth_impact_bps_per_side == pytest.approx(0.225)
    assert contract.stress_depth_impact_bps_per_side == pytest.approx(1.165)
    assert contract.execution.nominal_latency_bps_per_side == pytest.approx(1.225)
    assert contract.execution.stress_latency_bps_per_side == pytest.approx(3.165)
    assert contract.execution.stress_visible_tail_bps_per_side == 0.0
    assert contract.execution.notional_usd == 75.0
    assert contract.execution.maximum_hold_bars == 288


def test_scaled_friction_rejects_aliased_liquidity() -> None:
    """A different market's depth profile cannot support the oil replay."""
    module = import_module("hypervector.research.hip3_oil_shock_reversion_friction")

    with pytest.raises(ValueError, match="liquidity profile symbol"):
        module.build_hip3_oil_friction_contract(
            symbol="xyz:BRENTOIL",
            venue_max_leverage=20.0,
            fee_profile=_fee_profile(),
            liquidity_profile=_liquidity_profile("xyz:CL"),
        )


def test_live_canary_tail_can_raise_but_not_lower_stress_friction() -> None:
    """Sparse live slippage is retained as a conservative sensitivity floor."""
    module = import_module("hypervector.research.hip3_oil_shock_reversion_friction")
    live = {
        "symbol": "xyz:BRENTOIL",
        "execution_authority": "none",
        "lifecycles": [
            {"entry": {"slippage_bps": -2.5}, "exit": {"slippage_bps": 8.46}},
            {"entry": {"slippage_bps": 0.12}, "exit": {"slippage_bps": -0.64}},
        ],
    }

    floor, observations = module.observed_live_slippage_floor(live, "xyz:BRENTOIL")
    contract = module.build_hip3_oil_friction_contract(
        symbol="xyz:BRENTOIL",
        venue_max_leverage=20.0,
        fee_profile=_fee_profile(),
        liquidity_profile=_liquidity_profile(),
        live_stress_floor_bps_per_side=floor,
        live_slippage_observations=observations,
    )

    assert floor == 8.46
    assert observations == 4
    assert contract.execution.stress_latency_bps_per_side == 8.46
    assert contract.live_stress_floor_bps_per_side == 8.46
