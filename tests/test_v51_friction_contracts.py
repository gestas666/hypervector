"""Exact modeled execution contracts for every v51 provider route."""

from hypervector.research.cohort_friction_contracts import modeled_contract


def test_v51_new_route_contracts_match_declared_execution_shapes() -> None:
    """BTC specialists and fresh15 HIP-3 routes retain auditable mechanics."""
    cases = {
        ("hulk_expansion_short_robust_v3", "BTC"): (
            "structural_clamped_bps",
            "reward_risk",
        ),
        ("liquidity_sweep_long_1h_stop60_target60_v2", "BTC"): (
            "fixed_bps",
            "fixed_bps",
        ),
        (
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "xyz:SP500",
        ): ("fixed_bps", "none"),
        (
            "hip3_breakout_pressure_sp500_spcx_fresh15s_bidirectional_v3",
            "xyz:SPCX",
        ): ("fixed_bps", "none"),
    }

    for (strategy, symbol), (stop_policy, target_policy) in cases.items():
        contract = modeled_contract(strategy, symbol)
        assert contract is not None
        assert contract.stop_policy == stop_policy
        assert contract.target_policy == target_policy
        assert contract.evidence_source
