"""Tests for the frozen one-minute order-flow impulse contract."""

from __future__ import annotations

import pytest

from hypervector.research.orderflow_impulse_contract import (
    OrderFlowImpulseConfig,
    default_orderflow_impulse_config,
)


def test_default_contract_matches_registered_development_protocol() -> None:
    """The public default must preserve the predeclared economics."""
    config = default_orderflow_impulse_config()

    assert config.symbols == ("BTC", "SOL")
    assert config.warmup_minutes == 10_080
    assert config.target_bps == 30.0
    assert config.stop_bps == 20.0
    assert config.maximum_hold_minutes == 15
    assert config.nominal_round_trip_cost_bps == 13.0
    assert config.stress_round_trip_cost_bps == 20.0
    assert config.execution_authority == "none"


def test_contract_rejects_cost_or_timing_inconsistency() -> None:
    """Invalid costs and timing must fail rather than silently normalize."""
    with pytest.raises(ValueError, match="stress cost"):
        OrderFlowImpulseConfig(stress_round_trip_cost_bps=12.0)
    with pytest.raises(ValueError, match="round-trip cost identity"):
        OrderFlowImpulseConfig(nominal_round_trip_cost_bps=12.0)
    with pytest.raises(ValueError, match="warmup"):
        OrderFlowImpulseConfig(warmup_minutes=0)
