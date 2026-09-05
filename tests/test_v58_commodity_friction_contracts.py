"""Exact modeled friction for V58 commodity pressure routes."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_friction_contracts import modeled_contract

_STRATEGY = "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)


@pytest.mark.parametrize(
    ("symbol", "entry_slippage_bps"),
    [("xyz:SNDK", 4.107450915961097), ("xyz:BRENTOIL", 0.120219761725604)],
)
def test_v58_commodity_pressure_has_exact_modeled_friction(
    symbol: str,
    entry_slippage_bps: float,
) -> None:
    """Every executable V58 commodity route must have a cited live shape."""
    contract = modeled_contract(_STRATEGY, symbol)

    assert contract is not None
    assert contract.entry_fee_bps == pytest.approx(0.864)
    assert contract.entry_slippage_bps == pytest.approx(entry_slippage_bps)
    assert contract.stop_policy == "fixed_bps"
    assert contract.stop_bps == pytest.approx(80.0)
    assert contract.maximum_hold_seconds == 86_400
    assert contract.target_policy == "none"
    assert contract.evidence_source == _EVIDENCE
