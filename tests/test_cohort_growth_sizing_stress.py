"""Tests for report-only $5k cohort growth sizing stress."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_growth_sizing_stress import (
    AssetGrowthStressInput,
    VisibleCostQuantiles,
    build_growth_sizing_stress,
)


def test_projects_ten_slot_percentage_sizing_and_correlated_stop_wave() -> None:
    """The report keeps configured-roster and hypothetical capacity risk distinct."""
    report = build_growth_sizing_stress(
        equity_usd=5_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        maximum_positions=10,
        assets=tuple(_asset(symbol) for symbol in _symbols()),
    )

    assert report["schema_version"] == 3
    assert report["mode"] == "cohort_growth_sizing_stress_v3"
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_sizing_change": False,
        "performance_gate": False,
        "balance_gate": False,
        "profit_forecast": False,
    }
    plan = report["sizing_plan"]
    assert plan["planned_margin_usd_per_slot"] == pytest.approx(150.0)
    assert plan["planned_notional_usd_per_slot"] == pytest.approx(750.0)
    assert plan["configured_assets"] == 9
    assert plan["unused_capacity_slots"] == 1
    assert plan["actual_roster_maximum_margin_fraction"] == pytest.approx(0.27)
    assert plan["ten_slot_maximum_margin_fraction"] == pytest.approx(0.30)

    btc = report["by_asset"]["BTC"]
    assert btc["current_profile_cap_usd"] == pytest.approx(25.0)
    assert btc["current_profile_cap_binding_at_target_equity"] is True
    assert btc["candidate_nonbinding_cap_usd"] == pytest.approx(750.0)
    assert btc["adverse_24h_funding_bps"] == pytest.approx(3.0)
    assert btc["p90"]["total_loss_bps"] == pytest.approx(94.0)
    assert btc["p90"]["total_loss_usd"] == pytest.approx(7.05)
    assert btc["p90"]["adverse_exit_visible_cost_bps"] == pytest.approx(2.0)
    assert "visible_cost_bps" not in btc["p90"]

    actual = report["portfolio_stress"]["configured_asset_roster"]
    assert actual["p90_stop_wave_loss_usd"] == pytest.approx(63.45)
    assert actual["p90_stop_wave_loss_pct_equity"] == pytest.approx(1.269)
    assert actual["isolated_margin_at_risk_usd"] == pytest.approx(1_350.0)
    hypothetical = report["portfolio_stress"]["hypothetical_ten_slot_capacity"]
    assert hypothetical["p90_stop_wave_loss_usd"] == pytest.approx(70.5)
    assert hypothetical["isolated_margin_at_risk_usd"] == pytest.approx(1_500.0)
    assert hypothetical["synthetic_slot_count"] == 1
    assert report["repeated_wave_sensitivity"]["three_p90_waves_loss_usd"] == (
        pytest.approx(211.5)
    )


def test_asset_costs_preserve_distinct_fee_liquidity_and_funding_inputs() -> None:
    """A high-friction asset remains visible rather than pooled away."""
    asset = _asset(
        "xyz:SNDK",
        fee_bps=0.864,
        p50=3.0,
        p90=20.0,
        p99=65.0,
        hourly_rate=-0.0002,
    )

    report = build_growth_sizing_stress(
        equity_usd=5_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        maximum_positions=1,
        assets=(asset,),
    )

    row = report["by_asset"]["xyz:SNDK"]
    assert row["round_trip_taker_fee_bps"] == pytest.approx(1.728)
    assert row["adverse_24h_funding_bps"] == pytest.approx(48.0)
    assert row["p99"]["adverse_exit_visible_cost_bps"] == pytest.approx(65.0)
    assert row["p99"]["total_loss_bps"] == pytest.approx(194.728)


def test_hypothetical_slot_uses_worst_asset_at_each_quantile() -> None:
    """A p99 winner cannot understate the synthetic slot at p50 or p90."""
    report = build_growth_sizing_stress(
        equity_usd=5_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        maximum_positions=3,
        assets=(
            _asset("BTC", p50=10.0, p90=10.0, p99=10.0),
            _asset("ETH", p50=1.0, p90=9.0, p99=100.0),
        ),
    )

    actual = report["portfolio_stress"]["configured_asset_roster"]
    capacity = report["portfolio_stress"]["hypothetical_ten_slot_capacity"]
    assert capacity["p50_stop_wave_loss_usd"] - actual[
        "p50_stop_wave_loss_usd"
    ] == pytest.approx(report["by_asset"]["BTC"]["p50"]["total_loss_usd"])
    assert capacity["p90_stop_wave_loss_usd"] - actual[
        "p90_stop_wave_loss_usd"
    ] == pytest.approx(report["by_asset"]["BTC"]["p90"]["total_loss_usd"])
    assert capacity["p99_stop_wave_loss_usd"] - actual[
        "p99_stop_wave_loss_usd"
    ] == pytest.approx(report["by_asset"]["ETH"]["p99"]["total_loss_usd"])
    assert capacity["synthetic_slot_policy"] == "repeat_highest_loss_per_quantile"


def test_report_declares_asynchronous_evidence_and_no_joint_loss_probability() -> None:
    """Mixed live/archive windows remain deterministic sensitivity evidence."""
    report = build_growth_sizing_stress(
        equity_usd=5_000.0,
        margin_fraction=0.03,
        leverage=5.0,
        maximum_positions=1,
        assets=(_asset("BTC"),),
    )

    assert "asset_liquidity_windows_are_not_synchronized" in report["limitations"]
    assert "no_joint_loss_probability_is_estimated" in report["limitations"]


def test_rejects_capacity_below_asset_count_and_duplicate_assets() -> None:
    """Portfolio topology cannot be silently truncated or overwritten."""
    with pytest.raises(ValueError, match="maximum positions must cover assets"):
        build_growth_sizing_stress(
            equity_usd=5_000.0,
            margin_fraction=0.03,
            leverage=5.0,
            maximum_positions=1,
            assets=(_asset("BTC"), _asset("ETH")),
        )
    with pytest.raises(ValueError, match="asset symbols must be unique"):
        build_growth_sizing_stress(
            equity_usd=5_000.0,
            margin_fraction=0.03,
            leverage=5.0,
            maximum_positions=2,
            assets=(_asset("BTC"), _asset("BTC")),
        )


def _symbols() -> tuple[str, ...]:
    return (
        "BTC",
        "ETH",
        "SOL",
        "HYPE",
        "xyz:SP500",
        "xyz:SPCX",
        "xyz:SNDK",
        "xyz:GOLD",
        "xyz:BRENTOIL",
    )


def _asset(
    symbol: str,
    *,
    fee_bps: float = 4.5,
    p50: float = 1.0,
    p90: float = 2.0,
    p99: float = 4.0,
    hourly_rate: float = 0.0000125,
) -> AssetGrowthStressInput:
    return AssetGrowthStressInput(
        symbol=symbol,
        stop_bps=80.0,
        one_way_taker_fee_bps=fee_bps,
        visible_cost=VisibleCostQuantiles(
            sample_count=240,
            complete_rate=1.0,
            p50=p50,
            p90=p90,
            p99=p99,
        ),
        latest_hourly_funding_rate=hourly_rate,
        current_profile_cap_usd=25.0 if symbol in {"BTC", "ETH"} else 75.0,
    )
