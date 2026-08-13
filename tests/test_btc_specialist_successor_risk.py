"""Deterministic sizing and stop-loss exposure for the BTC successor."""

from pathlib import Path

import pytest

from hypervector.research.btc_specialist_successor_risk import (
    build_btc_specialist_successor_risk,
)

_PROFILE = Path("configs/multi_asset_bidirectional_btc_specialists_candidate_v43.toml")
_CORRECTED_PROFILE = Path(
    "configs/multi_asset_bidirectional_btc_specialists_corrected_candidate_v44.toml"
)


def test_v43_risk_scales_linearly_at_current_and_growth_equity() -> None:
    """The $500 and $5K stages use one percent policy and explicit fees."""
    report = build_btc_specialist_successor_risk(
        _PROFILE,
        account_values_usd=(500.0, 5_000.0),
        taker_fee_bps_per_side=4.5,
    )
    scenarios = {row["account_value_usd"]: row for row in report["scenarios"]}
    growth = scenarios[5_000.0]
    routes = {row["strategy_id"]: row for row in growth["btc_routes"]}
    short = routes["hulk_expansion_short_robust_v3"]
    long = routes["liquidity_sweep_long_1h_stop60_v1"]

    assert report["execution_authority"] == "none"
    assert report["maximum_positions_capacity"] == 10
    assert report["actual_asset_slots"] == 3
    assert report["maximum_simultaneous_margin_fraction"] == pytest.approx(
        0.23203607689345356
    )
    assert report["maximum_simultaneous_gross_account_multiple"] == pytest.approx(
        1.1601803844672678
    )
    assert short["planned_notional_usd"] == pytest.approx(3_333.333333333333)
    assert short["maximum_stop_loss_plus_round_trip_fees_usd"] == pytest.approx(28.0)
    assert short["maximum_stop_loss_fraction"] == pytest.approx(0.0056)
    assert short["maximum_stop_net_target_usd"] == pytest.approx(72.0)
    assert long["planned_notional_usd"] == pytest.approx(4_166.666666666667)
    assert long["stop_loss_plus_round_trip_fees_usd"] == pytest.approx(28.75)
    assert long["stop_loss_fraction"] == pytest.approx(0.00575)
    assert long["net_target_usd"] == pytest.approx(7.361111111111112)


def test_v43_risk_discloses_evidence_and_fee_limitations() -> None:
    """Sizing arithmetic cannot be mistaken for proven strategy edge."""
    report = build_btc_specialist_successor_risk(
        _PROFILE,
        account_values_usd=(500.0,),
        taker_fee_bps_per_side=4.5,
    )

    assert report["evidence_state"] == "two_distinct_forward_exact_n1_routes"
    assert report["repeatability_established"] is False
    assert report["fee_evidence"]["one_way_taker_fee_bps"] == 4.5
    assert "point-in-time" in report["fee_evidence"]["limitation"].lower()
    assert report["risk_limitations"]
    assert all(len(value["sha256"]) == 64 for value in report["inputs"].values())


def test_v44_risk_uses_corrected_target_and_honest_evidence_state() -> None:
    """The corrected taker challenger has distinct payoff and provenance."""
    report = build_btc_specialist_successor_risk(
        _CORRECTED_PROFILE,
        account_values_usd=(500.0, 5_000.0),
        taker_fee_bps_per_side=4.5,
    )
    routes = {row["strategy_id"]: row for row in report["scenarios"][1]["btc_routes"]}
    long = routes["liquidity_sweep_long_1h_stop60_target60_v2"]

    assert report["evidence_state"] == "short_n1_long_taker_path_unresolved"
    assert report["repeatability_established"] is False
    assert long["target_bps"] == pytest.approx(60.0)
    assert long["net_target_usd"] == pytest.approx(21.25)
    assert report["inputs"]["long_forward"]["path"].endswith(
        "btc_liquidity_sweep_taker_parity_20260811_v2.json"
    )
