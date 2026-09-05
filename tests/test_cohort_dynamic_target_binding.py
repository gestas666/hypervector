"""Exact dynamic-target propagation through cohort entry plumbing."""

from __future__ import annotations

import pytest

from hypervector.live.bidirectional_intents import (
    BidirectionalIntentRouter,
    PositionState,
    RoutingAction,
    StrategyCapability,
    StrategyIntent,
)
from hypervector.live.cohort_entry_submission import stale_entry_before_submission
from hypervector.live.cohort_execution_contract_selection import bind_execution_plan
from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
    ProviderExecutionContract,
)


def _contract() -> ProviderExecutionContract:
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="absolute_anchor",
        maximum_hold_seconds=22_500,
        provider_recipe_exit_policy="honor",
    )


def _action(*, side: str, target_anchor: float) -> RoutingAction:
    return RoutingAction(
        action="enter",
        strategy_id="spcx_cash_open",
        symbol="xyz:SPCX",
        side=side,
        decision_time_ms=1_000,
        reference_price=100.0,
        target_anchor=target_anchor,
    )


def test_router_preserves_dynamic_target_anchor() -> None:
    """A selected entry must retain the decision-time absolute target."""
    router = BidirectionalIntentRouter(
        (
            StrategyCapability(
                "spcx_cash_open", "xyz:SPCX", frozenset({"long", "short"}), 10
            ),
        ),
        maximum_positions=1,
    )
    intent = StrategyIntent(
        strategy_id="spcx_cash_open",
        symbol="xyz:SPCX",
        side="long",
        decision_time_ms=1_000,
        reference_price=99.0,
        reason="cash_open_gap_fade",
        target_anchor=100.0,
    )

    report = router.route(
        (intent,), positions={"xyz:SPCX": PositionState("xyz:SPCX", None)}
    )

    assert report.actions[0].target_anchor == 100.0


def test_absolute_target_round_trips_and_requires_favorable_fill() -> None:
    """Restart recovery must preserve the exact favorable target price."""
    long_plan = _contract().bind(
        strategy_id="spcx_cash_open", stop_anchor=None, target_anchor=101.0
    )
    recovered = BoundExecutionPlan.from_payload(long_plan.as_payload())

    assert recovered == long_plan
    assert recovered.target_price(entry_price=100.0, side="long") == 101.0
    with pytest.raises(CohortExecutionPlanError, match="favorable"):
        recovered.target_price(entry_price=102.0, side="long")

    short_plan = _contract().bind(
        strategy_id="spcx_cash_open", stop_anchor=None, target_anchor=99.0
    )
    assert short_plan.target_price(entry_price=100.0, side="short") == 99.0


def test_absolute_target_binding_fails_without_anchor() -> None:
    """An incomplete target cannot silently become a target-free entry."""
    with pytest.raises(CohortExecutionPlanError, match="target_anchor"):
        _contract().bind(
            strategy_id="spcx_cash_open", stop_anchor=None, target_anchor=None
        )


def test_execution_selection_binds_action_target_and_stale_copy_retains_it() -> None:
    """Selection and submission diagnostics must carry identical target evidence."""
    action = _action(side="long", target_anchor=101.0)
    plan = bind_execution_plan({"spcx_cash_open": _contract()}, action)
    withheld = stale_entry_before_submission(
        action,
        observed_ms=32_000,
        delays={("spcx_cash_open", "xyz:SPCX"): 30_000},
    )

    assert plan is not None
    assert plan.target_anchor == 101.0
    assert withheld is not None
    assert withheld.intent.target_anchor == 101.0
