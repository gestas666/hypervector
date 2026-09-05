"""Exact source-contract tests for HIP-3 shadow route friction."""

from __future__ import annotations

import pytest

from hypervector.live.hip3_breakout_shadow_specs import SP500_SHADOW_SPEC
from hypervector.research.hip3_shadow_route_friction import shadow_route_friction


def test_source_native_observer_contract_supplies_only_residual_latency() -> None:
    """Accept exact observer identity without fabricating development selection."""
    fee, latency = shadow_route_friction(
        _observer_contract(), _fee_evidence(), SP500_SHADOW_SPEC
    )

    assert fee == pytest.approx(0.864)
    assert latency == pytest.approx(0.0)


def test_source_native_observer_contract_rejects_route_config_drift() -> None:
    """Fail closed if observer friction evidence aliases another signal config."""
    contract = _observer_contract()
    contract["route"]["config"]["fast_ema"] = 9

    with pytest.raises(ValueError, match="signal config"):
        shadow_route_friction(contract, _fee_evidence(), SP500_SHADOW_SPEC)


def _observer_contract() -> dict[str, object]:
    return {
        "schema_version": "hip3_shadow_observer_route_contract_v1",
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "symbol": "xyz:SP500",
        "route": {
            "provider_id": "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "profile_id": "sp500_fresh15_pressure_shadow_research_v3",
            "timeframe": "15m",
            "family": "breakout_pressure",
            "config": {
                "breakout_lookback_bars": 32,
                "fast_ema": 21,
                "slow_ema": 55,
                "minimum_abs_imbalance": 0.1,
                "maximum_stop_bps": 120.0,
            },
        },
        "friction": {"nominal_latency_bps_per_side": 0.0},
    }


def _fee_evidence() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "profile": {
            "symbol": "xyz:SP500",
            "fees": {"one_way_taker_fee_bps": 0.864},
        },
    }
