"""Tests for the report-only SOL route-priority interaction replay."""

from __future__ import annotations

from hypervector.research.current_cohort_shared_portfolio import CohortOutcome
from hypervector.research.shared_trade_portfolio import SharedTradeOutcome
from hypervector.research.sol_route_priority_interaction import (
    BREAKOUT_STRATEGY,
    CURRENT_STATIC_PRIORITY,
    HULK_STRATEGY,
    RANGE_FIRST_STATIC_PRIORITY,
    RANGE_STRATEGY,
    build_sol_route_priority_interaction,
)


def _trade(
    identity: str,
    strategy: str,
    entry: int,
    exit_: int,
    net_pnl: float,
    *,
    side: str = "long",
) -> CohortOutcome:
    """Return one fixed-cap SOL lifecycle."""
    return CohortOutcome(
        strategy,
        side,
        SharedTradeOutcome(
            trade_id=identity,
            symbol="SOL",
            entry_time_ms=entry,
            exit_time_ms=exit_,
            source_equity_usd=500.0,
            margin_fraction=0.03,
            entry_fee_usd=0.03375,
            net_pnl_usd=net_pnl,
            outcome="maximum_hold",
        ),
    )


def test_two_arms_change_only_simultaneous_flat_boundary_owner() -> None:
    """The frozen priority counterfactual must change a simultaneous owner."""
    outcomes = (
        _trade("breakout", BREAKOUT_STRATEGY, 1_000, 2_000, -1.0),
        _trade("range", RANGE_STRATEGY, 1_000, 2_000, 2.0),
        _trade("hulk", HULK_STRATEGY, 3_000, 4_000, 0.5),
    )

    artifact = build_sol_route_priority_interaction(
        outcomes,
        development_end_ms=10_000,
        opened_final_start_ms=20_000,
        opened_final_end_ms=30_000,
        source_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    current = artifact["development"]["arms"]["current_static_priority"]
    range_first = artifact["development"]["arms"]["range_first_static_priority"]
    assert current["priority"] == list(CURRENT_STATIC_PRIORITY)
    assert range_first["priority"] == list(RANGE_FIRST_STATIC_PRIORITY)
    assert current["accepted_by_strategy"] == {
        BREAKOUT_STRATEGY: 1,
        HULK_STRATEGY: 1,
    }
    assert range_first["accepted_by_strategy"] == {
        HULK_STRATEGY: 1,
        RANGE_STRATEGY: 1,
    }
    assert current["rejected_by_strategy_reason"] == {
        f"{RANGE_STRATEGY}|symbol_occupied": 1
    }


def test_priority_cannot_evict_an_already_open_lifecycle() -> None:
    """A later high-priority signal must remain rejected while SOL is open."""
    outcomes = (
        _trade("breakout", BREAKOUT_STRATEGY, 1_000, 5_000, 1.0),
        _trade("range", RANGE_STRATEGY, 2_000, 3_000, 9.0),
        _trade("hulk", HULK_STRATEGY, 6_000, 7_000, 0.5),
    )

    artifact = build_sol_route_priority_interaction(
        outcomes,
        development_end_ms=10_000,
        opened_final_start_ms=20_000,
        opened_final_end_ms=30_000,
        source_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    for arm in artifact["development"]["arms"].values():
        assert arm["accepted_by_strategy"][BREAKOUT_STRATEGY] == 1
        assert arm["rejected_by_strategy_reason"] == {
            f"{RANGE_STRATEGY}|symbol_occupied": 1
        }


def test_artifact_purges_cross_boundary_outcomes_and_seals_selection() -> None:
    """Only fully resolved phase outcomes may enter each independent replay."""
    outcomes = (
        _trade("development", HULK_STRATEGY, 1_000, 2_000, 1.0),
        _trade("crossing", RANGE_STRATEGY, 9_000, 11_000, 5.0),
        _trade("final", BREAKOUT_STRATEGY, 20_000, 21_000, -0.5, side="short"),
    )

    artifact = build_sol_route_priority_interaction(
        outcomes,
        development_end_ms=10_000,
        opened_final_start_ms=20_000,
        opened_final_end_ms=30_000,
        source_evidence={"fixture": {"sha256": "0" * 64, "bytes": 1}},
    )

    assert artifact["input_trade_counts"] == {
        "development": 1,
        "opened_final_confirmation": 1,
        "purged_or_out_of_scope": 1,
    }
    assert artifact["development"]["used_for_selection"] is True
    assert artifact["opened_final_confirmation"]["used_for_selection"] is False
    assert artifact["trial_accounting"] == {
        "priority_arms": 2,
        "priority_orders_tested": [
            list(CURRENT_STATIC_PRIORITY),
            list(RANGE_FIRST_STATIC_PRIORITY),
        ],
        "parameter_sweeps": 0,
    }
    assert artifact["execution_authority"] == "none"
    assert artifact["automatic_promotion"] is False
    assert artifact["runtime_strategy_changed"] is False
