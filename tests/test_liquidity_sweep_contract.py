"""Contract tests for the preregistered five-minute sweep challenger."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.research.liquidity_sweep_contract import (
    LiquiditySweepConfig,
)


def test_default_contract_matches_preregistration() -> None:
    """The executable contract must retain the frozen research assumptions."""
    config = LiquiditySweepConfig()

    assert config.symbols == ("BTC", "SOL")
    assert config.structure_lookback_bars == 12
    assert config.reward_risk_multiple == 2.0
    assert config.maximum_hold_bars == 72
    assert config.nominal_round_trip_cost_bps == 13.0
    assert config.stress_round_trip_cost_bps == 20.0
    assert config.execution_authority == "none"


def test_contract_rejects_inconsistent_friction_identity() -> None:
    """Reported friction cannot disagree with fee and slippage components."""
    with pytest.raises(ValueError, match="round-trip cost identity"):
        replace(LiquiditySweepConfig(), nominal_round_trip_cost_bps=12.0)
