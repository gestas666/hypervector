"""Tests for the complete preregistered IBIT creation experiment report."""

from __future__ import annotations

import pytest

from btc_ibit_creation_fixtures import ibit_creation_history, ibit_market
from hypervector.research.btc_ibit_creation_experiment import (
    BtcIbitCreationCell,
    build_btc_ibit_creation_report,
    evaluate_btc_ibit_creation_acceptance,
)
from hypervector.research.btc_ibit_creation_replay import (
    evaluate_btc_ibit_creation_long,
)


_SCENARIOS = {
    "nominal": (2.0, 0),
    "stress": (5.0, 0),
    "publication_delay_24h": (2.0, 1440),
}
_ARMS = {
    "ibit_two_creation_persistence_candidate",
    "ibit_single_creation_onset_control",
    "ibit_two_redemption_persistence_long_placebo",
    "v58_liquidity_sweep_long_control",
    "no_action",
}


def test_report_publishes_all_45_rows_and_sparse_failure_evidence() -> None:
    """Every arm and scenario remains visible when the candidate is sparse."""
    result = build_btc_ibit_creation_report(_complete_cells())

    rows = result.report["summary_rows"]
    assert len(rows) == 45
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
    assert result.report["authority"]["execution_authority"] == "none"
    assert any("previously opened" in value for value in result.report["limitations"])
    assert result.trade_rows


def test_report_rejects_duplicate_or_incomplete_matrix() -> None:
    """A missing or duplicated cell cannot disappear from the report."""
    cells = _complete_cells()

    with pytest.raises(ValueError, match="duplicate or incomplete"):
        build_btc_ibit_creation_report(cells[:-1])
    with pytest.raises(ValueError, match="duplicate or incomplete"):
        build_btc_ibit_creation_report((*cells, cells[0]))


def test_redemption_placebo_fails_only_if_it_matches_both_oos_partitions() -> None:
    """Directional specificity uses the exact jointly frozen placebo rule."""
    rows = _acceptance_rows(validation_placebo=11.0, holdout_placebo=9.0)

    one_partition = evaluate_btc_ibit_creation_acceptance(rows)

    assert one_partition["candidate_supported"] is True
    both_rows = _acceptance_rows(validation_placebo=11.0, holdout_placebo=10.0)
    both = evaluate_btc_ibit_creation_acceptance(both_rows)
    assert both["candidate_supported"] is False
    assert "redemption_long_placebo_not_directionally_specific" in both["failed_checks"]


def _complete_cells() -> tuple[BtcIbitCreationCell, ...]:
    bars = ibit_market()
    history = ibit_creation_history()
    replays = {
        scenario: evaluate_btc_ibit_creation_long(
            bars,
            history,
            slippage,
            publication_delay_minutes=delay,
        )
        for scenario, (slippage, delay) in _SCENARIOS.items()
    }
    return tuple(
        BtcIbitCreationCell(partition, scenario, 90.0, replays[scenario])
        for partition in ("development", "validation", "pseudo_holdout")
        for scenario in _SCENARIOS
    )


def _acceptance_rows(
    *,
    validation_placebo: float,
    holdout_placebo: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for partition in ("validation", "pseudo_holdout"):
        for scenario in _SCENARIOS:
            placebo = (
                validation_placebo if partition == "validation" else holdout_placebo
            )
            for arm, pnl in (
                ("ibit_two_creation_persistence_candidate", 10.0),
                ("ibit_single_creation_onset_control", 2.0),
                ("ibit_two_redemption_persistence_long_placebo", placebo),
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
    candidate = arm == "ibit_two_creation_persistence_candidate"
    return {
        "partition": partition,
        "scenario": scenario,
        "arm": arm,
        "completed_trades": 10 if candidate else 1,
        "net_pnl_usd": pnl,
        "profit_factor": 2.0 if candidate else 1.1,
        "net_pnl_excluding_largest_winner_usd": 5.0 if candidate else pnl,
        "liquidations": 0,
        "insolvent": False,
    }
