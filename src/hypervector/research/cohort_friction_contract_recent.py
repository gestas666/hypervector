"""Modeled contracts for recent additive provider identities."""

from dataclasses import replace
from functools import cache

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
_V89_NOMINAL_CONTRACT_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v89_hourly_nominal_friction_contracts_20260907_v1.json"
)
_V90_HOURLY_DONCHIAN20 = "hourly_donchian_20_10_atr20_bidirectional_v1"
_V90_ADVERSE_ENTRY_SLIPPAGE_BPS = 5.5
_V90_ROSTER_SCREEN_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v90_expansion_screen_20260920_v1/exit_policy_v90_roster_63d.json"
)
_V90_BREADTH_SCREEN_EVIDENCE = (
    "data/logs/research/bidirectional_cohort/"
    "v90_expansion_screen_20260920_v1/screen_breadth_H1.json"
)
_V94_STRONG_SHORT_DONCHIAN20 = "hourly_donchian_20_10_atr20_strong_short_v1"
_V94_WEAK_SHORT_RESCORE_EVIDENCE = (
    "docs/research-journal/v94-weak-short-rescore-20260924-v1.json"
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


def v89_hourly_modeled_contracts() -> dict[tuple[str, str], ModeledExecutionContract]:
    """Return exact V89 nominal replay assumptions, not observed venue costs."""
    contract = ModeledExecutionContract(
        entry_liquidity="taker",
        entry_fee_bps=0.9,
        entry_slippage_bps=2.5,
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20.0,
        maximum_stop_bps=250.0,
        maximum_hold_seconds=86_400,
        maximum_hold_policy="fixed",
        hard_maximum_hold_seconds=None,
        target_policy="none",
        target_liquidity=None,
        target_bps=None,
        target_r_multiple=None,
        evidence_source=_V89_NOMINAL_CONTRACT_EVIDENCE,
    )
    return {
        ("hourly_band20_reentry_atr20_bidirectional_v1", "xyz:SPCX"): contract,
        ("hourly_donchian_20_10_atr20_bidirectional_v1", "xyz:SNDK"): contract,
        ("hourly_donchian_8_4_atr20_bidirectional_v1", "xyz:BRENTOIL"): contract,
    }


@cache
def v90_hourly_modeled_contracts() -> dict[tuple[str, str], ModeledExecutionContract]:
    """Return the V90 replay assumptions for the routes it moved or added.

    Derived from the V89 hourly contract by ``replace`` so the execution shape has
    one source of truth. Each route is bound to the **adverse** cost arm of the
    screen it cites (``declared_grid.costs.adverse`` in the evidence file): 5.5 bps
    entry slippage, 0.9 bps fee per side on growth-mode HIP-3 markets and 4.5 bps
    on the core perp. That is the only arm in those files whose fee convention
    matches V89's, and it is above the measured live rates (0.864 / 4.32 fees,
    0.8 bps entry slippage), so friction parity compares live fills against a
    conservative modelled number. Only routes with a published screen cell are
    listed, so an unresearched symbol still resolves to no contract.
    """
    base = v89_hourly_modeled_contracts()[(_V90_HOURLY_DONCHIAN20, "xyz:SNDK")]
    routes = {
        "SOL": (4.5, _V90_ROSTER_SCREEN_EVIDENCE),
        "xyz:BRENTOIL": (0.9, _V90_ROSTER_SCREEN_EVIDENCE),
        "xyz:TSLA": (0.9, _V90_BREADTH_SCREEN_EVIDENCE),
    }
    return {
        (_V90_HOURLY_DONCHIAN20, symbol): replace(
            base,
            entry_fee_bps=fee,
            entry_slippage_bps=_V90_ADVERSE_ENTRY_SLIPPAGE_BPS,
            evidence_source=evidence,
        )
        for symbol, (fee, evidence) in routes.items()
    }


@cache
def v94_strong_short_modeled_contracts() -> dict[
    tuple[str, str], ModeledExecutionContract
]:
    """Return the V94 strong-short replay assumptions for the four Donchian routes.

    The execution shape is the V89 hourly contract, unchanged. The pre-registered
    re-score ran every route at the V90 screen grid's measured and adverse arms;
    each route here is bound to the **adverse** arm (5.5 bps entry slippage, 0.9
    bps fee on HIP-3 and 4.5 bps on the core perp), as the V90 routes are. That
    includes xyz:SNDK, whose v1 route keeps the frozen V89 nominal contract.
    """
    base = v89_hourly_modeled_contracts()[(_V90_HOURLY_DONCHIAN20, "xyz:SNDK")]
    fees = {"SOL": 4.5, "xyz:SNDK": 0.9, "xyz:BRENTOIL": 0.9, "xyz:TSLA": 0.9}
    return {
        (_V94_STRONG_SHORT_DONCHIAN20, symbol): replace(
            base,
            entry_fee_bps=fee,
            entry_slippage_bps=_V90_ADVERSE_ENTRY_SLIPPAGE_BPS,
            evidence_source=_V94_WEAK_SHORT_RESCORE_EVIDENCE,
        )
        for symbol, fee in fees.items()
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
