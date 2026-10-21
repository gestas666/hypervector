"""Bounded regime-aware maximum-hold policy tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from hypervector.live.cohort_execution_plan import (
    BoundExecutionPlan,
    CohortExecutionPlanError,
    ProviderExecutionContract,
)
from hypervector.live.cohort_maximum_hold_policy import (
    maximum_hold_evaluations,
    maximum_hold_exit_reason,
    update_latest_evaluations,
)
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


def test_supported_position_extends_only_until_hard_deadline() -> None:
    """Aligned structure may pass the soft timer but not the hard cap."""
    plan = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    provider = _evaluation("hype", "TREND_UP", "TREND_UP", "TREND_UP")
    canonical = _evaluation(
        "test_breakout_1m", "TREND_UP", "TREND_UP", "TREND_UP"
    )

    assert (
        maximum_hold_exit_reason(
            plan,
            28_800_000,
            "long",
            provider,
            canonical,
            observed_ms=1_000,
        )
        is None
    )
    assert maximum_hold_exit_reason(plan, 86_400_000, "long", provider, canonical) == (
        "hard_maximum_hold_seconds"
    )


@pytest.mark.parametrize(
    ("provider_age_ms", "canonical_age_ms", "expected"),
    (
        (60_000, 60_000, None),
        (60_001, 60_000, "maximum_hold_evidence_stale"),
        (60_000, 60_001, "maximum_hold_evidence_stale"),
        (-1, 0, "maximum_hold_evidence_future"),
    ),
)
def test_extension_requires_complete_fresh_evidence(
    provider_age_ms: int,
    canonical_age_ms: int,
    expected: str | None,
) -> None:
    """Only complete nonfuture evidence inside the persisted bound may extend."""
    observed_ms = 100_000
    plan = _plan(
        policy="extend_while_regime_supported",
        hard_seconds=86_400,
        evidence_age_seconds=60,
    )
    provider = _evaluation_at("hype", observed_ms - provider_age_ms)
    canonical = _evaluation_at(
        "canonical_regime_telemetry_v1", observed_ms - canonical_age_ms
    )

    assert (
        maximum_hold_exit_reason(
            plan,
            28_800_000,
            "long",
            provider,
            canonical,
            observed_ms=observed_ms,
        )
        == expected
    )


def test_extension_exits_when_either_required_source_is_missing() -> None:
    """One supportive source cannot success-shape a partial evidence path."""
    observed_ms = 100_000
    plan = _plan(
        policy="extend_while_regime_supported",
        hard_seconds=86_400,
        evidence_age_seconds=60,
    )
    supported = _evaluation_at("hype", observed_ms)

    assert (
        maximum_hold_exit_reason(
            plan, 28_800_000, "long", supported, None, observed_ms=observed_ms
        )
        == "maximum_hold_evidence_missing"
    )
    assert (
        maximum_hold_exit_reason(
            plan, 28_800_000, "long", None, supported, observed_ms=observed_ms
        )
        == "maximum_hold_evidence_missing"
    )


def test_legacy_extension_without_age_contract_fails_closed() -> None:
    """A restored legacy plan cannot extend without a persisted age bound."""
    observed_ms = 100_000
    plan = _plan(
        policy="extend_while_regime_supported",
        hard_seconds=86_400,
        preserve_missing_evidence_age=True,
    )
    supported = _evaluation_at("hype", observed_ms)

    assert (
        maximum_hold_exit_reason(
            plan,
            28_800_000,
            "long",
            supported,
            supported,
            observed_ms=observed_ms,
        )
        == "maximum_hold_evidence_contract_missing"
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    (
        (None, "maximum_hold_evidence_missing"),
        ("UNKNOWN", "maximum_hold_seconds"),
        ("RANGE", "maximum_hold_seconds"),
        ("TREND_DOWN", "maximum_hold_seconds"),
    ),
)
def test_soft_deadline_exits_without_directional_support(
    state: str | None,
    expected: str,
) -> None:
    """Missing, mixed, or opposed evidence cannot silently extend risk."""
    plan = _plan(policy="extend_while_regime_supported", hard_seconds=86_400)
    provider = None if state is None else _evaluation("hype", state, state, state)
    canonical = (
        None
        if state is None
        else _evaluation("test_breakout_1m", state, state, state)
    )

    assert (
        maximum_hold_exit_reason(
            plan,
            28_800_000,
            "long",
            provider,
            canonical,
            observed_ms=1_000,
        )
        == expected
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
        maximum_hold_evidence_maximum_age_seconds=60,
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


def test_same_poll_batch_preserves_a_recipe_exit_over_a_later_hold() -> None:
    """A delayed poll must expose every one-shot exit before advancing state."""
    exit_row = replace(
        _evaluation_at("hype", 1_500),
        decision_action="close_long",
        reason="opposite_hype_alignment",
        exit_sides=frozenset({"long"}),
        exit_reason="opposite_hype_alignment",
    )
    later_hold = _evaluation_at("hype", 2_000)

    latest = update_latest_evaluations({}, (exit_row, later_hold))

    assert latest[("hype", "HYPE")] == exit_row


@pytest.mark.parametrize("hard_seconds", [None, 28_800, 1])
def test_extension_contract_requires_a_later_hard_deadline(
    hard_seconds: int | None,
) -> None:
    """An extension policy must retain a finite, later terminal deadline."""
    with pytest.raises(CohortExecutionPlanError, match="hard maximum hold"):
        _plan(policy="extend_while_regime_supported", hard_seconds=hard_seconds)


def _plan(
    *,
    policy: str,
    hard_seconds: int | None,
    evidence_age_seconds: int | None = None,
    preserve_missing_evidence_age: bool = False,
) -> BoundExecutionPlan:
    maximum_age = (
        60
        if (
            policy == "extend_while_regime_supported"
            and evidence_age_seconds is None
            and not preserve_missing_evidence_age
        )
        else evidence_age_seconds
    )
    return ProviderExecutionContract(
        entry_liquidity="taker_ioc",
        stop_policy="fixed_bps",
        stop_bps=80.0,
        target_policy="none",
        maximum_hold_seconds=28_800,
        maximum_hold_policy=policy,
        hard_maximum_hold_seconds=hard_seconds,
        maximum_hold_evidence_maximum_age_seconds=maximum_age,
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


def _evaluation_at(strategy_id: str, decision_time_ms: int) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="HYPE",
        decision_time_ms=decision_time_ms,
        reference_price=50.0,
        decision_action="hold",
        eligible=False,
        reason="test",
        side="long",
        readiness=SignalReadiness("long", 1, 1, (), ("TEST",), {}),
        primary_regime="TREND_UP",
        state_1m="TREND_UP",
        state_5m="TREND_UP",
        context_15m="TREND_UP",
    )
