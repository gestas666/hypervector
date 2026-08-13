"""Tests for the report-only lean successor portfolio comparison."""

from __future__ import annotations

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.evidence_selected_portfolio import PrioritizedPortfolioConfig
from hypervector.research.lean_successor_portfolio import (
    EvidenceWindow,
    SuccessorVariant,
    apply_incremental_round_trip_cost,
    evaluate_successor_comparison,
)
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome

RANGE = "range_onset_bidirectional_v1"
PULLBACK = "eth_breakout_precompression_pullback_bidirectional_v1"
SPCX = "hip3_swing_ha_sp500_spcx_bidirectional_v2"
SOL_ROUTE = (RANGE, "SOL")
ETH_RANGE_ROUTE = (RANGE, "ETH")
ETH_PULLBACK_ROUTE = (PULLBACK, "ETH")
SPCX_ROUTE = (SPCX, "xyz:SPCX")


def _outcome(
    route: tuple[str, str],
    index: int,
    net: float,
    *,
    side: str = "long",
) -> CohortOutcome:
    """Build one normalized completed lifecycle fixture."""
    strategy, symbol = route
    entry = 1_000 + index * 100
    source = SharedTradeOutcome(
        f"{strategy}|{symbol}|{index}",
        symbol,
        entry,
        entry + 50,
        500.0,
        0.03,
        0.01,
        net,
        "fixture_exit",
    )
    return CohortOutcome(strategy, side, source)


def _variants() -> tuple[SuccessorVariant, ...]:
    """Return the fixed additive comparison surface."""
    return (
        SuccessorVariant("sol_range_control", (SOL_ROUTE,)),
        SuccessorVariant(
            "sol_range_spcx",
            (SOL_ROUTE, SPCX_ROUTE),
            baseline_variant_id="sol_range_control",
        ),
        SuccessorVariant(
            "sol_range_spcx_eth_pullback",
            (SOL_ROUTE, SPCX_ROUTE, ETH_PULLBACK_ROUTE),
            baseline_variant_id="sol_range_spcx",
        ),
        SuccessorVariant(
            "sol_range_spcx_eth_dual_mtf",
            (SOL_ROUTE, SPCX_ROUTE, ETH_RANGE_ROUTE),
            baseline_variant_id="sol_range_spcx",
        ),
    )


def test_incremental_cost_applies_exact_route_notional_haircut() -> None:
    """Seven additional bps must bridge the 13-to-20-bps stress contract."""
    rows = (
        _outcome(SOL_ROUTE, 0, 1.0),
        _outcome(ETH_RANGE_ROUTE, 1, 1.0),
    )

    stressed = apply_incremental_round_trip_cost(
        rows,
        {SOL_ROUTE: 75.0, ETH_RANGE_ROUTE: 25.0},
        incremental_bps=7.0,
    )

    assert stressed[0].outcome.net_pnl_usd == 1.0 - 75.0 * 7.0 / 10_000.0
    assert stressed[1].outcome.net_pnl_usd == 1.0 - 25.0 * 7.0 / 10_000.0
    assert [row.trade_id for row in stressed] == [row.trade_id for row in rows]


def test_comparison_replays_variants_and_reports_marginal_value() -> None:
    """Each additive route must be measured against its declared control."""
    nominal = {
        SOL_ROUTE: (_outcome(SOL_ROUTE, 0, 1.0),),
        SPCX_ROUTE: (_outcome(SPCX_ROUTE, 1, -0.25, side="short"),),
        ETH_PULLBACK_ROUTE: (_outcome(ETH_PULLBACK_ROUTE, 2, -0.5),),
        ETH_RANGE_ROUTE: (_outcome(ETH_RANGE_ROUTE, 3, 0.75, side="short"),),
    }
    stress = {
        route: tuple(
            _outcome(route, index + 10, row.outcome.net_pnl_usd - 0.1, side=row.side)
            for index, row in enumerate(rows)
        )
        for route, rows in nominal.items()
    }
    config = PrioritizedPortfolioConfig(500.0, 3, (RANGE, PULLBACK, SPCX))

    artifact = evaluate_successor_comparison(
        {"nominal": nominal, "stress": stress},
        _variants(),
        (EvidenceWindow("full_opened", None, None),),
        config,
    )

    assert artifact["execution_authority"] == "none"
    assert artifact["report_only"] is True
    nominal_reports = artifact["windows"]["full_opened"]["nominal"]
    assert nominal_reports["sol_range_control"]["net_pnl_usd"] == 1.0
    assert nominal_reports["sol_range_spcx"]["net_pnl_usd"] == 0.75
    assert nominal_reports["sol_range_spcx_eth_pullback"]["net_pnl_usd"] == 0.25
    assert nominal_reports["sol_range_spcx_eth_dual_mtf"]["net_pnl_usd"] == 1.5
    marginal = artifact["marginal_deltas"]["full_opened"]["nominal"]
    assert marginal["sol_range_spcx"]["baseline_variant_id"] == "sol_range_control"
    assert marginal["sol_range_spcx"]["net_pnl_usd"] == -0.25
    assert marginal["sol_range_spcx_eth_pullback"]["net_pnl_usd"] == -0.5
    assert marginal["sol_range_spcx_eth_dual_mtf"]["net_pnl_usd"] == 0.75


def test_comparison_reports_concentration_and_missing_direction() -> None:
    """A positive aggregate may not hide largest-winner or side concentration."""
    routes = {
        SOL_ROUTE: (
            _outcome(SOL_ROUTE, 0, 2.0),
            _outcome(SOL_ROUTE, 1, -0.5),
        ),
        SPCX_ROUTE: (_outcome(SPCX_ROUTE, 2, -0.25),),
        ETH_PULLBACK_ROUTE: (_outcome(ETH_PULLBACK_ROUTE, 3, 0.1),),
        ETH_RANGE_ROUTE: (_outcome(ETH_RANGE_ROUTE, 4, 0.2),),
    }
    config = PrioritizedPortfolioConfig(500.0, 3, (RANGE, PULLBACK, SPCX))

    artifact = evaluate_successor_comparison(
        {"nominal": routes, "stress": routes},
        _variants(),
        (EvidenceWindow("full_opened", None, None),),
        config,
    )

    report = artifact["windows"]["full_opened"]["nominal"]["sol_range_control"]
    assert report["concentration"]["net_excluding_largest_winner_usd"] == -0.5
    assert report["coverage"]["missing_route_sides"] == [f"{RANGE}|SOL|short"]
    assert report["completed_trades"] == 2


def test_window_filters_on_entry_timestamp_without_censoring_exit() -> None:
    """The fixed windows select entries and retain their later completed exits."""
    rows = {
        SOL_ROUTE: (
            _outcome(SOL_ROUTE, 0, 1.0),
            _outcome(SOL_ROUTE, 1, 2.0),
        ),
        SPCX_ROUTE: (_outcome(SPCX_ROUTE, 2, 0.1),),
        ETH_PULLBACK_ROUTE: (_outcome(ETH_PULLBACK_ROUTE, 3, 0.1),),
        ETH_RANGE_ROUTE: (_outcome(ETH_RANGE_ROUTE, 4, 0.1),),
    }
    config = PrioritizedPortfolioConfig(500.0, 3, (RANGE, PULLBACK, SPCX))

    artifact = evaluate_successor_comparison(
        {"nominal": rows, "stress": rows},
        _variants(),
        (EvidenceWindow("first", 1_000, 1_100),),
        config,
    )

    report = artifact["windows"]["first"]["nominal"]["sol_range_control"]
    assert report["completed_trades"] == 1
    assert report["net_pnl_usd"] == 1.0
