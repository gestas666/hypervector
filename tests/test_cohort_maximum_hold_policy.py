"""Bounded regime-aware maximum-hold policy tests."""

from __future__ import annotations

import pytest

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
    ProviderExecutionContract,
)
from hypervector.live.cohort_maximum_hold_policy import (
    maximum_hold_evaluations,
    maximum_hold_exit_reason,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


def test_supported_position_extends_only_until_hard_deadline() -> None:
    """Aligned structure may pass the soft timer but not the hard cap."""
    plan = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    provider = _evaluation("hype", "TREND_UP", "TREND_UP", "TREND_UP")
    canonical = _evaluation(
        "range_onset_bidirectional_v1", "TREND_UP", "TREND_UP", "TREND_UP"
    )

    assert (
        maximum_hold_exit_reason(plan, 28_800_000, "long", provider, canonical) is None
    )
    assert maximum_hold_exit_reason(plan, 86_400_000, "long", provider, canonical) == (
        "hard_maximum_hold_seconds"
    )


@pytest.mark.parametrize("state", [None, "UNKNOWN", "RANGE", "TREND_DOWN"])
def test_soft_deadline_exits_without_directional_support(state: str | None) -> None:
    """Missing, mixed, or opposed evidence cannot silently extend risk."""
    plan = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    provider = None if state is None else _evaluation("hype", state, state, state)
    canonical = (
        None
        if state is None
        else _evaluation("range_onset_bidirectional_v1", state, state, state)
    )

    assert maximum_hold_exit_reason(plan, 28_800_000, "long", provider, canonical) == (
        "maximum_hold_seconds"
    )


def test_fixed_policy_preserves_existing_timer_behavior() -> None:
    """Existing persisted plans remain fixed-timer contracts."""
    plan = _plan(policy="fixed", hard_seconds=None)
    supported = _evaluation("hype", "TREND_UP", "TREND_UP", "TREND_UP")

    assert (
        maximum_hold_exit_reason(plan, 28_799_999, "long", supported, supported) is None
    )
    assert maximum_hold_exit_reason(plan, 28_800_000, "long", supported, supported) == (
        "maximum_hold_seconds"
    )


def test_maximum_hold_reads_independent_canonical_regime_identity() -> None:
    """Removing Range execution must not remove open-position regime context."""
    plan = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    provider = _evaluation("hype", "TREND_UP", "TREND_UP", "TREND_UP")
    canonical = _evaluation(
        "canonical_regime_telemetry_v1",
        "TREND_UP",
        "TREND_UP",
        "TREND_UP",
    )

    assert maximum_hold_evaluations(
        plan,
        "HYPE",
        {
            ("hype", "HYPE"): provider,
            ("canonical_regime_telemetry_v1", "HYPE"): canonical,
        },
    ) == (provider, canonical)


def test_manual_provider_identity_uses_the_same_maximum_hold_evidence() -> None:
    """An operator entry must not lose the provider's regime extension evidence."""
    base = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    plan = ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=28_800,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_seconds=86_400,
    ).bind(strategy_id="operator_override:hype", stop_anchor=None)
    provider = _evaluation("hype", "TREND_UP", "TREND_UP", "TREND_UP")
    canonical = _evaluation(
        "canonical_regime_telemetry_v1",
        "TREND_UP",
        "TREND_UP",
        "TREND_UP",
    )
    evaluations = {
        ("hype", "HYPE"): provider,
        ("canonical_regime_telemetry_v1", "HYPE"): canonical,
    }

    assert maximum_hold_evaluations(base, "HYPE", evaluations) == (provider, canonical)
    assert maximum_hold_evaluations(plan, "HYPE", evaluations) == (provider, canonical)


@pytest.mark.parametrize("hard_seconds", [None, 28_800, 1])
def test_extension_contract_requires_a_later_hard_deadline(
    hard_seconds: int | None,
) -> None:
    """An extension policy must retain a finite, later terminal deadline."""
    with pytest.raises(CohortExecutionPlanError, match="hard maximum hold"):
        _plan(policy="extend_while_regime_supported", hard_seconds=hard_seconds)


def _plan(*, policy: str, hard_seconds: int | None) -> BoundExecutionPlan:
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=28_800,
        maximum_hold_policy=policy,
        hard_maximum_hold_seconds=hard_seconds,
    ).bind(strategy_id="hype", stop_anchor=None)


def _evaluation(
    strategy_id: str,
    primary: str,
    state_5m: str,
    context_15m: str,
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="HYPE",
        decision_time_ms=1_000,
        reference_price=50.0,
        decision_action="hold",
        eligible=False,
        reason="test",
        side=None,
        readiness=SignalReadiness(None, 1, 1, (), ("TEST",), {}),
        primary_regime=primary,
        state_1m=primary,
        state_5m=state_5m,
        context_15m=context_15m,
    )
