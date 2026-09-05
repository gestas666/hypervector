"""Modeled contracts for recent additive provider identities."""

from hypervector.research.cohort_friction_contract_models import (
    ModeledExecutionContract,
)

_V58_COMMODITY_FRESH15 = (
    "hip3_breakout_pressure_sndk_gold_brent_fresh15s_bidirectional_v2"
)
_V76_SNDK_FRESH15 = "hip3_breakout_pressure_sndk_fresh15s_bidirectional_v3"
_V79_ETH_RANGE_LONG = "eth_range_onset_long_dual_mtf_v2"
_V79_SOL_RANGE_SHORT = "sol_range_onset_short_dual_mtf_v2"
_V79_ZEC_DONCHIAN_LONG = "zec_donchian_20_10_atr20_long_v1"
_V79_SPCX_CASH_LONG = "hip3_spcx_cash_session_fresh15_long_v4"
_V58_STRESS_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v58_eight_asset_growth_sizing_stress_20260819_v1.json"
)
_V84_V79_CONTRACT_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v84_v79_friction_contract_completion_20260903_v1.json"
)


def v58_commodity_fresh15_modeled_contracts() -> dict[
    tuple[str, str], ModeledExecutionContract
]:
    """Return source-bound mechanics for the two V58 commodity routes."""
    entry_slippage = {
        "xyz:SNDK": 4.107450915961097,
        "xyz:BRENTOIL": 0.120219761725604,
    }
    return {
        (_V58_COMMODITY_FRESH15, symbol): ModeledExecutionContract(
            "taker",
            0.864,
            slippage,
            "fixed_bps",
            80.0,
            None,
            None,
            86_400,
            "fixed",
            None,
            "none",
            None,
            None,
            None,
            _V58_STRESS_EVIDENCE,
        )
        for symbol, slippage in entry_slippage.items()
    }


def v76_sndk_fresh15_modeled_contract() -> tuple[
    tuple[str, str], ModeledExecutionContract
]:
    """Return V76's identity-only SNDK split with its frozen V58 mechanics."""
    source = v58_commodity_fresh15_modeled_contracts()[
        (_V58_COMMODITY_FRESH15, "xyz:SNDK")
    ]
    return (_V76_SNDK_FRESH15, "xyz:SNDK"), source


def spcx_cash_open_modeled_contract() -> ModeledExecutionContract:
    """Return the frozen development-shaped SPCX cash-open mechanics."""
    return ModeledExecutionContract(
        "taker",
        0.864,
        1.0,
        "fixed_bps",
        80.0,
        None,
        None,
        22_500,
        "fixed",
        None,
        "absolute_anchor",
        "maker",
        None,
        None,
        "data/logs/research/"
        "xyz_spcx_cash_open_gap_reversal_development_20260817_v2.json",
    )


def v79_route_modeled_contracts() -> dict[tuple[str, str], ModeledExecutionContract]:
    """Return source-bound execution shapes for V79's four additive routes."""
    return {
        (_V79_ETH_RANGE_LONG, "ETH"): _v79_contract(
            4.5, None, "fixed_bps", 60.0, None, None, 172_800, "none", None
        ),
        (_V79_SOL_RANGE_SHORT, "SOL"): _v79_contract(
            4.5, None, "fixed_bps", 60.0, None, None, 172_800, "none", None
        ),
        (_V79_ZEC_DONCHIAN_LONG, "ZEC"): _v79_contract(
            4.5,
            2.5,
            "structural_clamped_bps",
            None,
            20.0,
            250.0,
            2_592_000,
            "none",
            None,
        ),
        (_V79_SPCX_CASH_LONG, "xyz:SPCX"): _v79_contract(
            0.864,
            2.7515676541,
            "fixed_bps",
            60.0,
            None,
            None,
            22_500,
            "fixed_bps",
            120.0,
        ),
    }


def _v79_contract(
    entry_fee_bps: float,
    entry_slippage_bps: float | None,
    stop_policy: str,
    stop_bps: float | None,
    minimum_stop_bps: float | None,
    maximum_stop_bps: float | None,
    maximum_hold_seconds: int,
    target_policy: str,
    target_bps: float | None,
) -> ModeledExecutionContract:
    target_liquidity = "maker" if target_policy != "none" else None
    return ModeledExecutionContract(
        "taker",
        entry_fee_bps,
        entry_slippage_bps,
        stop_policy,
        stop_bps,
        minimum_stop_bps,
        maximum_stop_bps,
        maximum_hold_seconds,
        "fixed",
        None,
        target_policy,
        target_liquidity,
        target_bps,
        None,
        _V84_V79_CONTRACT_EVIDENCE,
    )
