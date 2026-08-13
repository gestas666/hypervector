"""Shared-capital contracts for attributed Apex cohort outcomes."""

from __future__ import annotations

import pytest

from hypervector.research.apex_cohort_portfolio import (
    ApexAttributedOutcome,
    ApexCohortPortfolioConfig,
    replay_apex_cohort,
)


def _outcome(
    identity: str,
    candidate: str,
    *,
    symbol: str = "BTC",
    entry: int = 1_000,
    exit: int = 2_000,
    margin: float = 1_500.0,
    fee: float = 5.0,
    pnl: float = 50.0,
) -> ApexAttributedOutcome:
    return ApexAttributedOutcome(
        outcome_id=identity,
        candidate=candidate,
        symbol=symbol,
        entry_time_ms=entry,
        exit_time_ms=exit,
        requested_margin_usd=margin,
        entry_fee_usd=fee,
        net_pnl_usd=pnl,
    )


def test_same_symbol_conflict_uses_deterministic_candidate_priority() -> None:
    market_maker = _outcome("mm", "apex_regime_mm_v2")
    mean_reversion = _outcome("mr", "apex_mean_reversion_v2")

    report = replay_apex_cohort((mean_reversion, market_maker))

    assert [item.outcome_id for item in report.accepted] == ["mm"]
    assert report.rejected[0].outcome_id == "mr"
    assert report.rejected[0].reason == "symbol_occupied"


def test_nonoverlapping_outcomes_use_one_balance_without_double_counting_fees() -> None:
    first = _outcome("one", "apex_regime_mm_v2", pnl=50.0, fee=5.0)
    second = _outcome(
        "two",
        "apex_mean_reversion_v2",
        entry=2_000,
        exit=3_000,
        pnl=-20.0,
        fee=4.0,
    )

    report = replay_apex_cohort((first, second))

    assert report.final_equity_usd == pytest.approx(15_030.0)
    assert report.net_pnl_usd == pytest.approx(30.0)
    assert report.total_entry_fees_usd == pytest.approx(9.0)
    assert report.maximum_concurrent_positions == 1


def test_aggregate_margin_cap_rejects_second_symbol_without_mutating_equity() -> None:
    config = ApexCohortPortfolioConfig(maximum_reserved_margin_fraction=0.15)
    btc = _outcome("btc", "apex_regime_mm_v2", margin=1_500.0)
    sol = _outcome(
        "sol",
        "apex_mean_reversion_v2",
        symbol="SOL",
        margin=1_500.0,
    )

    report = replay_apex_cohort((btc, sol), config)

    assert len(report.accepted) == 1
    assert report.rejected[0].reason == "aggregate_margin_cap"
    assert report.total_entry_fees_usd == pytest.approx(5.0)


def test_strategy_pnl_and_fee_attribution_reconciles_to_portfolio() -> None:
    first = _outcome("one", "apex_regime_mm_v2", pnl=50.0, fee=5.0)
    second = _outcome(
        "two",
        "apex_mean_reversion_v2",
        entry=2_000,
        exit=3_000,
        pnl=-20.0,
        fee=4.0,
    )

    report = replay_apex_cohort((first, second))

    assert report.strategy_net_pnl_usd == {
        "apex_regime_mm_v2": 50.0,
        "apex_mean_reversion_v2": -20.0,
    }
    assert report.strategy_entry_fees_usd == {
        "apex_regime_mm_v2": 5.0,
        "apex_mean_reversion_v2": 4.0,
    }
    assert sum(report.strategy_net_pnl_usd.values()) == pytest.approx(
        report.net_pnl_usd
    )


def test_invalid_overlapping_outcomes_from_same_candidate_are_rejected() -> None:
    first = _outcome("one", "apex_mean_reversion_v2")
    overlap = _outcome(
        "two",
        "apex_mean_reversion_v2",
        entry=1_500,
        exit=2_500,
    )

    report = replay_apex_cohort((first, overlap))

    assert len(report.accepted) == 1
    assert report.rejected[0].reason == "symbol_occupied"


def test_hulk_directional_has_priority_over_simultaneous_mm_measurement() -> None:
    """A validated directional intent wins a same-time BTC ownership conflict."""
    hulk = _outcome("hulk", "hulk_expansion_short_robust_v3", pnl=20.0)
    market_maker = _outcome("mm", "apex_regime_mm_v2", pnl=5.0)

    report = replay_apex_cohort((market_maker, hulk))

    assert [item.outcome_id for item in report.accepted] == ["hulk"]
    assert report.rejected[0].outcome_id == "mm"
    assert report.strategy_net_pnl_usd == {"hulk_expansion_short_robust_v3": 20.0}
