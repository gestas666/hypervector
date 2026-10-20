"""Equity-fraction stop-loss budgets compound with the entry sizing account value."""

from dataclasses import replace
import json
import math

import pytest

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    ProviderExecutionContract,
)
from hypervector.live.cohort_stop_risk_sizing import (
    StopRiskAccountValueError,
    StopRiskBudget,
    size_for_stop_risk,
)
from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.cohort_profile_stage import _toml
from hypervector.research.cohort_configuration_exit_policy import (
    provider_exit_expectation,
    provider_exit_policy_evidence,
)

EXIT_POLICY_V2 = "tests/fixtures/profiles/exit_policy_v2.toml"


def _plan(budget: StopRiskBudget | None = None) -> BoundExecutionPlan:
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=100,
        target_policy="none",
        maximum_hold_seconds=3600,
        stop_risk_budget=budget,
    ).bind(strategy_id="test", stop_anchor=None)


def _size(budget: StopRiskBudget, account_value_usd: float | None):
    return size_for_stop_risk(
        plan=_plan(budget),
        budget=budget,
        mark_price=100,
        side="long",
        entry_slippage_fraction=0.002,
        original_notional_usd=100_000,
        account_value_usd=account_value_usd,
    )


def test_fraction_only_budget_scales_with_the_entry_account_value() -> None:
    budget = StopRiskBudget(None, 20, 0.006)
    small, large = _size(budget, 4831.0), _size(budget, 9662.0)
    assert small.estimated_loss_usd == pytest.approx(0.006 * 4831.0)
    assert large.estimated_loss_usd == pytest.approx(0.006 * 9662.0)
    assert large.notional_usd == pytest.approx(2 * small.notional_usd)
    assert small.as_payload() == {
        "original_notional_usd": 100_000,
        "notional_usd": small.notional_usd,
        "quantity": small.quantity,
        "entry_bound": small.entry_bound,
        "stop_bound": small.stop_bound,
        "estimated_loss_usd": small.estimated_loss_usd,
        "maximum_loss_usd": None,
        "cost_buffer_bps": 20.0,
        "maximum_loss_fraction_of_equity": 0.006,
        "account_value_usd": 4831.0,
        "effective_maximum_loss_usd": pytest.approx(0.006 * 4831.0),
    }


@pytest.mark.parametrize(
    "account,expected", [(1000.0, 6.0), (4831.0, 25.0), (100_000.0, 25.0)]
)
def test_both_declared_budgets_bind_on_the_smaller_loss(
    account: float, expected: float
) -> None:
    result = _size(StopRiskBudget(25, 20, 0.006), account)
    assert result.estimated_loss_usd == pytest.approx(expected)
    assert result.as_payload()["effective_maximum_loss_usd"] == pytest.approx(expected)
    assert result.as_payload()["maximum_loss_usd"] == 25.0


def test_dollar_only_sizing_payload_is_the_legacy_row() -> None:
    result = _size(StopRiskBudget(10, 20), 5000.0)
    assert list(result.as_payload()) == [
        "original_notional_usd",
        "notional_usd",
        "quantity",
        "entry_bound",
        "stop_bound",
        "estimated_loss_usd",
        "maximum_loss_usd",
        "cost_buffer_bps",
    ]
    assert _size(StopRiskBudget(10, 20), None).as_payload() == result.as_payload()


@pytest.mark.parametrize(
    "account", [None, 0.0, -1.0, float("nan"), float("inf"), True, "5000"]
)
def test_fraction_budget_never_sizes_on_an_unusable_account_value(
    account: object,
) -> None:
    with pytest.raises(StopRiskAccountValueError, match="account value"):
        _size(StopRiskBudget(25, 20, 0.006), account)  # type: ignore[arg-type]
    assert issubclass(StopRiskAccountValueError, ValueError)


@pytest.mark.parametrize(
    "loss,buffer,fraction",
    [
        (None, 20, None),
        (None, 20, 0.0),
        (None, 20, -0.001),
        (None, 20, 0.0500001),
        (None, 20, 0.5),
        (None, 20, float("nan")),
        (None, 20, float("inf")),
        (None, 20, True),
        (25, 20, 0.0),
        (0, 20, 0.006),
    ],
)
def test_invalid_fraction_budget_is_refused(
    loss: float | None, buffer: float, fraction: float | None
) -> None:
    with pytest.raises(ValueError):
        StopRiskBudget(loss, buffer, fraction)


def test_fraction_at_the_five_percent_ceiling_is_accepted() -> None:
    assert StopRiskBudget(None, 20, 0.05).maximum_loss_fraction_of_equity == 0.05


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {"maximum_loss_fraction_of_equity": 0.006, "cost_buffer_bps": 20.0},
            StopRiskBudget(None, 20, 0.006),
        ),
        (
            {
                "maximum_loss_usd": 29,
                "maximum_loss_fraction_of_equity": 0.006,
                "cost_buffer_bps": 20,
            },
            StopRiskBudget(29, 20, 0.006),
        ),
        ({"maximum_loss_usd": 25, "cost_buffer_bps": 20}, StopRiskBudget(25, 20)),
    ],
)
def test_payload_declares_dollars_fraction_or_both(
    payload: dict[str, object], expected: StopRiskBudget
) -> None:
    budget = StopRiskBudget.from_payload(payload)
    assert budget == expected
    assert StopRiskBudget.from_payload(budget.as_payload()) == budget  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "payload",
    [
        {"cost_buffer_bps": 20},
        {"maximum_loss_fraction_of_equity": 0.006},
        {"maximum_loss_fraction_of_equity": "0.006", "cost_buffer_bps": 20},
        {"maximum_loss_fraction_of_equity": True, "cost_buffer_bps": 20},
        {"maximum_loss_fraction_of_equty": 0.006, "cost_buffer_bps": 20},
        {
            "maximum_loss_fraction_of_equity": 0.006,
            "cost_buffer_bps": 20,
            "maximum_loss_usd": None,
        },
    ],
)
def test_malformed_fraction_payload_is_refused(payload: object) -> None:
    with pytest.raises(ValueError):
        StopRiskBudget.from_payload(payload)


def test_unknown_budget_key_is_named_in_the_refusal() -> None:
    with pytest.raises(ValueError, match="maximum_loss_fraction_of_equty"):
        StopRiskBudget.from_payload(
            {"maximum_loss_fraction_of_equty": 0.006, "cost_buffer_bps": 20}
        )


def test_dollar_budget_payload_is_byte_identical_to_baseline() -> None:
    assert json.dumps(StopRiskBudget(25, 20).as_payload()) == (
        '{"maximum_loss_usd": 25.0, "cost_buffer_bps": 20.0}'
    )
    config = load_multi_asset_live_config(EXIT_POLICY_V2, mode="observe")
    for provider in config.providers:
        payload = provider.execution.as_payload()
        assert payload["stop_risk_budget"] == {
            "maximum_loss_usd": 25.0,
            "cost_buffer_bps": 20.0,
        }
        plan = provider.execution.bind(
            strategy_id=provider.strategy_id,
            stop_anchor=100.0
            if provider.execution.stop_policy == "structural_clamped_bps"
            else None,
        )
        assert "maximum_loss_fraction_of_equity" not in json.dumps(plan.as_payload())


def test_fraction_budget_round_trips_through_contract_plan_and_staging(
    tmp_path,
) -> None:
    config = load_multi_asset_live_config(EXIT_POLICY_V2, mode="observe")
    budget = StopRiskBudget(None, 20, 0.006)
    first = config.providers[0]
    changed = replace(
        first, execution=replace(first.execution, stop_risk_budget=budget)
    )
    contract = changed.execution
    assert ProviderExecutionContract.from_payload(contract.as_payload()) == contract
    assert contract.as_payload()["stop_risk_budget"] == {
        "cost_buffer_bps": 20.0,
        "maximum_loss_fraction_of_equity": 0.006,
    }
    plan = contract.bind(strategy_id="test", stop_anchor=None)
    assert BoundExecutionPlan.from_payload(plan.as_payload()) == plan
    candidate = replace(
        config, providers=(changed, *config.providers[1:]), transition_approval=None
    )
    assert (
        candidate.profile_fingerprint
        != replace(config, transition_approval=None).profile_fingerprint
    )
    target = tmp_path / "fraction.toml"
    target.write_text(_toml(candidate))
    loaded = load_multi_asset_live_config(target, mode="observe")
    assert loaded.profile_fingerprint == candidate.profile_fingerprint
    evidence = provider_exit_policy_evidence(provider_exit_expectation(loaded))
    assert evidence[first.strategy_id]["stop_risk_budget"] == {
        "cost_buffer_bps": 20.0,
        "maximum_loss_fraction_of_equity": 0.006,
    }
    untouched = evidence[config.providers[1].strategy_id]["stop_risk_budget"]
    assert untouched == {"maximum_loss_usd": 25.0, "cost_buffer_bps": 20.0}


def test_effective_loss_helper_matches_the_documented_minimum() -> None:
    budget = StopRiskBudget(29, 20, 0.006)
    assert budget.effective_maximum_loss_usd(4831.0) == pytest.approx(28.986)
    assert budget.effective_maximum_loss_usd(10_000.0) == 29.0
    assert StopRiskBudget(29, 20).effective_maximum_loss_usd(None) == 29.0
    assert math.isclose(
        StopRiskBudget(None, 20, 0.006).effective_maximum_loss_usd(1.0), 0.006
    )
