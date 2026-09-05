"""Tests for evidence-bound successor exposure sizing."""

from __future__ import annotations

import math

import pytest

from hypervector.research.v51_successor_exposure_ladder import (
    build_v51_successor_exposure_ladder,
)


def _disposition() -> dict[str, object]:
    return {
        "mode": "report_only",
        "execution_authority": "none",
        "automatic_live_change": False,
        "portfolio_conclusion": {"full_size_routes_supported": 0},
        "route_dispositions": [
            {
                "strategy_id": "hulk_expansion_short_robust_v3",
                "symbol": "BTC",
                "side": "short",
                "disposition": "conditional_successor_candidate_not_full_size",
            },
            {
                "strategy_id": "liquidity_sweep_long_1h_stop60_target60_v2",
                "symbol": "BTC",
                "side": "long",
                "disposition": "conditional_successor_candidate_selection_risk",
            },
            {
                "strategy_id": "range_onset_bidirectional_v1",
                "symbol": "ETH",
                "side": "long_short",
                "disposition": "retire_from_successor",
            },
            {
                "strategy_id": "hip3_breakout_pressure_v3",
                "symbol": "xyz:SP500",
                "side": "long_short",
                "disposition": "defer_pending_source_native_breadth",
            },
        ],
    }


def _build() -> dict[str, object]:
    return build_v51_successor_exposure_ladder(
        _disposition(),
        account_equity_usd=5_000.0,
        core_taker_fee_bps_per_side=4.32,
        hip3_taker_fee_bps_per_side=0.864,
        slippage_stress_bps_per_side=2.0,
    )


def test_ladder_restores_the_relative_canary_exposure_before_scaling() -> None:
    report = _build()

    tiers = {row["tier_id"]: row for row in report["exposure_tiers"]}
    assert tiers["canary_equivalent"]["notional_usd"] == 750.0
    assert tiers["provisional_growth"]["notional_usd"] == pytest.approx(
        2_698.6183074265985
    )
    assert tiers["corroborated_growth"]["notional_usd"] == 5_000.0
    assert tiers["expansion"]["notional_usd"] == 7_500.0
    assert tiers["provisional_growth"]["risk_budget_fraction"] == 0.005
    assert tiers["corroborated_growth"]["risk_budget_fraction"] == 0.01
    assert tiers["expansion"]["risk_budget_fraction"] == 0.015
    assert report["reference_canary"]["gross_account_fraction"] == 0.15


def test_current_evidence_caps_only_the_two_btc_routes_at_canary_size() -> None:
    report = _build()

    routes = {
        (row["strategy_id"], row["symbol"]): row
        for row in report["current_route_ceilings"]
    }
    hulk = routes[("hulk_expansion_short_robust_v3", "BTC")]
    sweep = routes[("liquidity_sweep_long_1h_stop60_target60_v2", "BTC")]
    assert hulk["maximum_proposal_tier"] == "canary_equivalent"
    assert sweep["maximum_proposal_tier"] == "canary_equivalent"
    assert hulk["maximum_proposed_notional_usd"] == 750.0
    assert sweep["maximum_proposed_notional_usd"] == 750.0
    assert (
        routes[("range_onset_bidirectional_v1", "ETH")]["maximum_proposed_notional_usd"]
        == 0.0
    )
    assert (
        routes[("hip3_breakout_pressure_v3", "xyz:SP500")][
            "maximum_proposed_notional_usd"
        ]
        == 0.0
    )
    assert report["portfolio_ceiling"]["simultaneous_asset_slots"] == 1


def test_loss_accounting_includes_exact_fee_class_and_route_stop() -> None:
    report = _build()

    routes = {row["strategy_id"]: row for row in report["current_route_ceilings"]}
    hulk = routes["hulk_expansion_short_robust_v3"]
    sweep = routes["liquidity_sweep_long_1h_stop60_target60_v2"]
    assert hulk["maximum_stop_bps"] == 75.0
    assert sweep["maximum_stop_bps"] == 60.0
    assert math.isclose(hulk["stop_plus_round_trip_friction_usd"], 6.573)
    assert math.isclose(sweep["stop_plus_round_trip_friction_usd"], 5.448)
    assert math.isclose(hulk["maximum_net_target_usd"], 15.927)
    assert math.isclose(sweep["maximum_net_target_usd"], 3.552)


def test_each_tier_quantifies_the_ten_slot_stop_fee_wave() -> None:
    report = _build()

    scenarios = {row["tier_id"]: row for row in report["ten_slot_capacity_scenarios"]}
    assert math.isclose(
        scenarios["canary_equivalent"]["all_core_stop_friction_wave_usd"], 69.48
    )
    assert math.isclose(
        scenarios["provisional_growth"]["all_core_stop_friction_wave_usd"],
        250.0,
    )
    assert math.isclose(
        scenarios["corroborated_growth"]["all_core_stop_friction_wave_usd"],
        463.2,
    )
    assert math.isclose(
        scenarios["expansion"]["all_core_stop_friction_wave_usd"], 694.8
    )
    assert scenarios["canary_equivalent"]["gross_account_exposure_multiple"] == 1.5
    assert scenarios["corroborated_growth"]["gross_account_exposure_multiple"] == 10.0
    assert scenarios["corroborated_growth"]["margin_fraction_at_10x"] == 1.0
    assert (
        scenarios["canary_equivalent"]["maximum_positions_with_20pct_margin_headroom"]
        == 10
    )
    assert (
        scenarios["corroborated_growth"]["maximum_positions_with_20pct_margin_headroom"]
        == 8
    )
    assert scenarios["expansion"]["maximum_positions_with_20pct_margin_headroom"] == 5
    assert (
        scenarios["corroborated_growth"]["ten_slot_margin_feasible_with_20pct_headroom"]
        is False
    )


def test_ladder_is_advisory_and_cannot_change_runtime_authority() -> None:
    report = _build()

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_live_change": False,
        "automatic_promotion": False,
        "runtime_performance_gate": False,
        "human_approval_required": True,
    }
    assert report["assessment"]["successor_live_ready"] is False
    assert report["assessment"]["growth_meaningful_portfolio_ready"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (("mode", "live"), ("execution_authority", "orders")),
)
def test_ladder_rejects_non_report_only_source(field: str, value: object) -> None:
    source = _disposition()
    source[field] = value

    with pytest.raises(ValueError, match="report-only"):
        build_v51_successor_exposure_ladder(
            source,
            account_equity_usd=5_000.0,
            core_taker_fee_bps_per_side=4.32,
            hip3_taker_fee_bps_per_side=0.864,
            slippage_stress_bps_per_side=2.0,
        )
