"""Dollar loss budget, fill-bound and compatibility contracts."""

from dataclasses import replace

import pytest

from hypervector.live.cohort_execution_plan import ProviderExecutionContract
from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError
from hypervector.live.cohort_stop_risk_sizing import StopRiskBudget, size_for_stop_risk


def _plan() -> ProviderExecutionContract:
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=100,
        target_policy="none",
        maximum_hold_seconds=3600,
    )


@pytest.mark.parametrize("side", ["long", "short"])
def test_budget_includes_adverse_entry_and_friction(side: str) -> None:
    plan = _plan().bind(strategy_id="test", stop_anchor=None)
    result = size_for_stop_risk(
        plan=plan,
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side=side,
        entry_slippage_fraction=0.002,
        original_notional_usd=2000,
    )
    assert result.notional_usd < 1000
    assert result.estimated_loss_usd == pytest.approx(10)
    assert (
        result.quantity
        * (abs(result.entry_bound - result.stop_bound) + result.entry_bound * 0.002)
        <= 10 + 1e-10
    )


def test_budget_does_not_increase_existing_notional() -> None:
    result = size_for_stop_risk(
        plan=_plan().bind(strategy_id="test", stop_anchor=None),
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side="long",
        entry_slippage_fraction=0.002,
        original_notional_usd=100,
    )
    assert result.notional_usd == 100


def test_structural_stop_uses_actual_bound_and_clamp() -> None:
    plan = replace(
        _plan(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20,
        maximum_stop_bps=250,
    ).bind(strategy_id="test", stop_anchor=90)
    result = size_for_stop_risk(
        plan=plan,
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side="long",
        entry_slippage_fraction=0.002,
        original_notional_usd=2000,
    )
    assert result.stop_bound == pytest.approx(100.2 * 0.975)
    assert result.estimated_loss_usd == pytest.approx(10)


@pytest.mark.parametrize(
    "loss,buffer", [(0, 20), (-1, 20), (True, 20), (10, -1), (10, float("nan"))]
)
def test_invalid_budget_is_refused(loss: float, buffer: float) -> None:
    with pytest.raises(ValueError):
        StopRiskBudget(loss, buffer)


def test_contract_round_trip_and_old_payload_compatibility() -> None:
    old = _plan()
    assert "stop_risk_budget" not in old.as_payload()
    contract = replace(old, stop_risk_budget=StopRiskBudget(10, 20))
    assert ProviderExecutionContract.from_payload(contract.as_payload()) == contract
    plan = contract.bind(strategy_id="test", stop_anchor=None)
    assert type(plan).from_payload(plan.as_payload()) == plan


@pytest.mark.parametrize("side,anchor", [("long", 98.0), ("short", 102.3)])
def test_all_modeled_fills_including_clamp_turning_point_fit_budget(
    side: str, anchor: float
) -> None:
    plan = replace(
        _plan(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20,
        maximum_stop_bps=250,
    ).bind(strategy_id="test", stop_anchor=anchor)
    result = size_for_stop_risk(
        plan=plan,
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side=side,
        entry_slippage_fraction=0.01,
        original_notional_usd=2000,
    )
    for step in range(201):
        fill = 99 + step / 100
        stop = plan.stop_price(entry_price=fill, side=side)
        loss = result.quantity * (abs(fill - stop) + fill * 0.002)
        assert loss <= 10 + 1e-10


def test_unreachable_structural_clamp_boundary_does_not_divide_by_zero() -> None:
    plan = replace(
        _plan(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20,
        maximum_stop_bps=10000,
    ).bind(strategy_id="test", stop_anchor=98)
    result = size_for_stop_risk(
        plan=plan,
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side="long",
        entry_slippage_fraction=0.002,
        original_notional_usd=2000,
    )
    assert result.estimated_loss_usd == pytest.approx(10)


def test_overflowed_fill_bound_is_refused() -> None:
    with pytest.raises(ValueError, match="fill bound"):
        size_for_stop_risk(
            plan=_plan().bind(strategy_id="test", stop_anchor=None),
            budget=StopRiskBudget(10, 20),
            mark_price=1e308,
            side="long",
            entry_slippage_fraction=0.9,
            original_notional_usd=2000,
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"maximum_loss_usd": 10},
        {"maximum_loss_usd": 10, "cost_buffer_bps": 20, "extra": 1},
        {"maximum_loss_usd": "10", "cost_buffer_bps": 20},
        {"maximum_loss_usd": 10, "cost_buffer_bps": True},
        {"maximum_loss_usd": 10, "cost_buffer_bps": 10000},
    ],
)
def test_malformed_payload_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        StopRiskBudget.from_payload(payload)


@pytest.mark.parametrize(
    "side,slip",
    [
        ("invalid", 0.002),
        ("long", -1),
        ("short", 1),
        ("long", float("nan")),
        ("long", True),
    ],
)
def test_invalid_fill_model_is_refused(side: str, slip: float) -> None:
    with pytest.raises(ValueError):
        size_for_stop_risk(
            plan=_plan().bind(strategy_id="test", stop_anchor=None),
            budget=StopRiskBudget(10, 20),
            mark_price=100,
            side=side,
            entry_slippage_fraction=slip,
            original_notional_usd=2000,
        )


@pytest.mark.parametrize(
    "side,anchor,adverse_bound",
    [
        ("long", 99.9, 100.2),
        ("long", 99.81, 100.2),
        ("short", 100.1, 99.8),
        ("short", 100.19, 99.8),
    ],
)
def test_structural_anchor_inside_modeled_fill_interval_sizes_from_adverse_bound(
    side: str, anchor: float, adverse_bound: float
) -> None:
    """A stop anchor closer than the slippage cap must not fault the entry before the order."""
    plan = replace(
        _plan(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20,
        maximum_stop_bps=250,
    ).bind(strategy_id="test", stop_anchor=anchor)
    result = size_for_stop_risk(
        plan=plan,
        budget=StopRiskBudget(10, 20),
        mark_price=100,
        side=side,
        entry_slippage_fraction=0.002,
        original_notional_usd=5000,
    )
    assert result.notional_usd < 5000
    assert result.entry_bound == pytest.approx(adverse_bound)
    assert result.estimated_loss_usd == pytest.approx(10)
    for step in range(401):
        fill = 99.8 + step / 1000
        try:
            stop = plan.stop_price(entry_price=fill, side=side)
        except CohortExecutionPlanError:
            continue
        assert result.quantity * (abs(fill - stop) + fill * 0.002) <= 10 + 1e-9


@pytest.mark.parametrize(
    "side,anchor", [("long", 100.0), ("long", 100.1), ("short", 100.0), ("short", 99.9)]
)
def test_structural_anchor_not_adverse_at_mark_is_refused(
    side: str, anchor: float
) -> None:
    plan = replace(
        _plan(),
        stop_policy="structural_clamped_bps",
        stop_bps=None,
        minimum_stop_bps=20,
        maximum_stop_bps=250,
    ).bind(strategy_id="test", stop_anchor=anchor)
    with pytest.raises(CohortExecutionPlanError):
        size_for_stop_risk(
            plan=plan,
            budget=StopRiskBudget(10, 20),
            mark_price=100,
            side=side,
            entry_slippage_fraction=0.002,
            original_notional_usd=2000,
        )
