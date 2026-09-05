"""Tests for the complete preregistered BTC DVOL-VRP experiment report."""

from __future__ import annotations

import pytest

from btc_dvol_vrp_fixtures import dvol_vrp_features, dvol_vrp_market
from hypervector.research.btc_dvol_vrp_experiment import (
    BtcDvolVrpCell,
    build_btc_dvol_vrp_report,
    evaluate_btc_dvol_vrp_acceptance,
)
from hypervector.research.btc_dvol_vrp_replay import evaluate_btc_dvol_vrp_long


_SCENARIOS = ("nominal", "stress", "delayed")
_ARMS = {
    "dvol_vrp_bullish_breakout_long",
    "price_only_bullish_breakout_long",
    "high_vrp_only_long",
    "low_vrp_bullish_breakout_long_placebo",
    "v58_liquidity_sweep_long_control",
    "no_action",
}


def test_report_publishes_all_54_rows_and_sparse_failure_evidence() -> None:
    """No performance result may abort or disappear from the full matrix."""
    result = build_btc_dvol_vrp_report(_complete_cells())

    rows = result.report["summary_rows"]
    assert len(rows) == 54
    assert len(result.report["comparisons"]) == 9
    assert {row["arm"] for row in rows} == _ARMS
    assert {row["scenario"] for row in rows} == set(_SCENARIOS)
    required = {
        "raw_signal_count",
        "completed_trades",
        "wins",
        "losses",
        "gross_market_pnl_usd",
        "net_pnl_usd",
        "profit_factor",
        "maximum_drawdown_pct",
        "net_pnl_excluding_largest_winner_usd",
        "fees_usd",
        "funding_usd",
        "liquidations",
        "insolvent",
        "same_bar_ambiguities",
        "gap_expired_entries",
        "forced_end_exits",
        "median_interarrival_hours",
        "events_per_week",
        "point_in_time_event_times_utc",
    }
    assert all(required.issubset(row) for row in rows)
    acceptance = result.report["acceptance"]
    assert acceptance["candidate_supported"] is False
    assert (
        "validation_nominal_minimum_ten_completed_trades" in acceptance["failed_checks"]
    )
    assert acceptance["live_promotion_authorized"] is False
    assert acceptance["retuning_authorized"] is False
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.report["delayed_scenario_cost_headroom"]
    assert "unfavorable_slices" in result.report
    assert result.trade_rows


def test_report_rejects_duplicate_or_incomplete_matrix() -> None:
    """A missing or duplicated replay cell is a technical failure."""
    cells = _complete_cells()

    with pytest.raises(ValueError, match="duplicate or incomplete"):
        build_btc_dvol_vrp_report(cells[:-1])
    with pytest.raises(ValueError, match="duplicate or incomplete"):
        build_btc_dvol_vrp_report((*cells, cells[0]))


def test_acceptance_enforces_price_sweep_and_placebo_specificity() -> None:
    """A survivor must add value and retain the preregistered mechanism sign."""
    passing = evaluate_btc_dvol_vrp_acceptance(_acceptance_rows())

    assert passing["candidate_supported"] is True
    placebo_both = evaluate_btc_dvol_vrp_acceptance(
        _acceptance_rows(validation_placebo=11.0, holdout_placebo=10.0)
    )
    assert "low_vrp_placebo_not_directionally_specific" in placebo_both["failed_checks"]
    price_failure = evaluate_btc_dvol_vrp_acceptance(
        _acceptance_rows(validation_price=12.0)
    )
    assert (
        "validation_nominal_candidate_exceeds_price_only"
        in price_failure["failed_checks"]
    )


def _complete_cells() -> tuple[BtcDvolVrpCell, ...]:
    bars = dvol_vrp_market(150)
    features = dvol_vrp_features()
    replays = {
        scenario: evaluate_btc_dvol_vrp_long(bars, features, scenario)
        for scenario in _SCENARIOS
    }
    return tuple(
        BtcDvolVrpCell(partition, scenario, 90.0, replays[scenario])
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in _SCENARIOS
    )


def _acceptance_rows(
    *,
    validation_placebo: float = 1.0,
    holdout_placebo: float = 1.0,
    validation_price: float = 2.0,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in _SCENARIOS:
            placebo = (
                validation_placebo if partition == "validation" else holdout_placebo
            )
            price = validation_price if partition == "validation" else 2.0
            for arm, pnl in (
                ("dvol_vrp_bullish_breakout_long", 10.0),
                ("price_only_bullish_breakout_long", price),
                ("high_vrp_only_long", 3.0),
                ("low_vrp_bullish_breakout_long_placebo", placebo),
                ("v58_liquidity_sweep_long_control", 1.0),
                ("no_action", 0.0),
            ):
                rows.append(_acceptance_row(partition, scenario, arm, pnl))
    return rows


def _acceptance_row(
    partition: str,
    scenario: str,
    arm: str,
    pnl: float,
) -> dict[str, object]:
    primary = arm == "dvol_vrp_bullish_breakout_long"
    return {
        "partition": partition,
        "scenario": scenario,
        "arm": arm,
        "completed_trades": 10 if primary else 1,
        "net_pnl_usd": pnl,
        "profit_factor": 2.0 if primary else 1.1,
        "net_pnl_excluding_largest_winner_usd": 5.0 if primary else pnl,
        "liquidations": 0,
        "insolvent": False,
    }
