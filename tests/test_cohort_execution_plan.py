"""Provider-specific execution-plan validation and price-resolution tests."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
    ProviderExecutionContract,
)


def test_fixed_stop_plan_round_trips_and_resolves_long_prices() -> None:
    """A fixed-stop/fixed-target contract remains restart-serializable."""
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=60.0,
        target_policy="fixed_bps",
        target_bps=26.6666666667,
        maximum_hold_seconds=86_400,
        safety_stop_overlay=True,
    )

    plan = contract.bind(strategy_id="source", stop_anchor=None)
    recovered = BoundExecutionPlan.from_payload(plan.as_payload())

    assert recovered == plan
    assert recovered.stop_price(entry_price=100.0, side="long") == pytest.approx(99.4)
    assert recovered.target_price(entry_price=100.0, side="long") == pytest.approx(
        100.266666666667
    )


def test_structural_plan_clamps_anchor_and_resolves_three_r_short_target() -> None:
    """The structural stop uses the adverse anchor within its declared bounds."""
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20.0,
        maximum_stop_bps=75.0,
        target_policy="reward_risk",
        target_r_multiple=3.0,
        maximum_hold_seconds=86_400,
    )

    plan = contract.bind(strategy_id="hulk", stop_anchor=101.0)

    assert plan.stop_price(entry_price=100.0, side="short") == pytest.approx(100.75)
    assert plan.target_price(entry_price=100.0, side="short") == pytest.approx(97.75)


def test_structural_plan_rejects_non_adverse_anchor_at_fill() -> None:
    """A stale structural anchor cannot silently become a favorable stop."""
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="structural_clamped_bps",
        minimum_stop_bps=20.0,
        maximum_stop_bps=75.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
    ).bind(strategy_id="hulk", stop_anchor=99.0)

    with pytest.raises(CohortExecutionPlanError, match="adverse"):
        plan.stop_price(entry_price=100.0, side="short")


def test_provider_recipe_exit_policy_defaults_ignore_and_round_trips_honor() -> None:
    """Recipe exits require explicit authority and survive restart when granted."""
    ignored = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
    )
    honored = ProviderExecutionContract.from_payload(
        ignored.as_payload() | {"provider_recipe_exit_policy": "honor"}
    )

    assert ignored.provider_recipe_exit_policy == "ignore"
    assert honored.provider_recipe_exit_policy == "honor"
    plan = honored.bind(strategy_id="hip3_swing", stop_anchor=None)
    assert BoundExecutionPlan.from_payload(plan.as_payload()) == plan


def test_unknown_provider_recipe_exit_policy_fails_fast() -> None:
    """A misspelled exit authority cannot silently become executable."""
    payload = {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "stop_bps": 80.0,
        "target_policy": "none",
        "maximum_hold_seconds": 86_400,
        "provider_recipe_exit_policy": "sometimes",
    }

    with pytest.raises(CohortExecutionPlanError, match="provider recipe exit"):
        ProviderExecutionContract.from_payload(payload)


def test_profit_lock_defaults_disabled_without_hidden_parameters() -> None:
    """Legacy contracts cannot acquire an executable profit lock by default."""
    contract = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=86_400,
    )

    assert contract.profit_lock_policy == "none"
    assert contract.profit_lock_activation_bps is None
    assert contract.profit_lock_floor_bps is None
    assert contract.profit_lock_giveback_bps is None


def test_completed_bar_profit_lock_round_trips_through_bound_plan() -> None:
    """Explicit provider lock parameters survive entry binding and restart."""
    contract = ProviderExecutionContract.from_payload(
        {
            "entry_liquidity": "taker_ioc",
            "stop_policy": "fixed_bps",
            "stop_bps": 80.0,
            "target_policy": "none",
            "maximum_hold_seconds": 86_400,
            "profit_lock_policy": "completed_bar_trailing",
            "profit_lock_activation_bps": 25.0,
            "profit_lock_floor_bps": 15.0,
            "profit_lock_giveback_bps": 10.0,
        }
    )

    plan = contract.bind(strategy_id="range_onset_bidirectional_v1", stop_anchor=None)

    assert BoundExecutionPlan.from_payload(plan.as_payload()) == plan
    assert plan.profit_lock_policy == "completed_bar_trailing"


@pytest.mark.parametrize(
    "updates",
    [
        {"profit_lock_policy": "completed_bar_trailing"},
        {"profit_lock_activation_bps": 25.0},
        {
            "profit_lock_policy": "completed_bar_trailing",
            "profit_lock_activation_bps": 10.0,
            "profit_lock_floor_bps": 15.0,
            "profit_lock_giveback_bps": 10.0,
        },
    ],
)
def test_incomplete_or_inconsistent_profit_lock_fails_fast(
    updates: dict[str, object],
) -> None:
    """Partial or impossible lock declarations cannot become executable."""
    payload: dict[str, object] = {
        "entry_liquidity": "taker_ioc",
        "stop_policy": "fixed_bps",
        "stop_bps": 80.0,
        "target_policy": "none",
        "maximum_hold_seconds": 86_400,
    }

    with pytest.raises(CohortExecutionPlanError, match="profit lock"):
        ProviderExecutionContract.from_payload(payload | updates)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "entry_liquidity": "taker_ioc",
            "stop_policy": "fixed_bps",
            "target_policy": "none",
            "maximum_hold_seconds": 1,
        },
        {
            "entry_liquidity": "taker_ioc",
            "stop_policy": "fixed_bps",
            "stop_bps": 80.0,
            "target_policy": "reward_risk",
            "maximum_hold_seconds": 1,
        },
    ],
)
def test_incomplete_contracts_fail_fast(kwargs: dict[str, object]) -> None:
    """Missing policy parameters cannot become success-shaped defaults."""
    with pytest.raises(CohortExecutionPlanError):
        ProviderExecutionContract(**kwargs)  # type: ignore[arg-type]
