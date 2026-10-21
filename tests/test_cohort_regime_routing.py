"""Causal regime preference tests for multi-provider routing conflicts."""

from __future__ import annotations

import pytest

from hypervector.live.bidirectional_intents import StrategyIntent
from hypervector.live.cohort_regime_routing import attach_regime_preferences
from hypervector.live.provider_evaluation import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness


def test_preferences_score_canonical_timeframes_relative_to_intent_side() -> None:
    """The same causal structure supports one side and opposes the other."""
    intents = (_intent("long"), _intent("short"))
    evaluation = _evaluation("TREND_UP", "TREND_DOWN", "TREND_DOWN")

    weighted = attach_regime_preferences(intents, (evaluation,))

    assert weighted[0].regime_alignment_score == pytest.approx(-4.0 / 6.0)
    assert weighted[0].regime_alignment_stance == "directionally_opposed"
    assert weighted[1].regime_alignment_score == pytest.approx(4.0 / 6.0)
    assert weighted[1].regime_alignment_stance == "directionally_supported"
    assert weighted[1].regime_decision_time_ms == evaluation.decision_time_ms
    assert weighted[1].regime_alignment_basis == "canonical_1m_5m_15m_1_3_2_v1"


def test_missing_canonical_context_does_not_invent_a_preference() -> None:
    """Absent regime evidence preserves an unweighted but routable intent."""
    intent = _intent("long")

    assert attach_regime_preferences((intent,), ()) == (intent,)


def test_future_canonical_append_cannot_change_an_earlier_intent() -> None:
    """Each intent uses only the latest canonical close available by its decision."""
    intent = _intent("long")
    causal = _evaluation(
        "TREND_UP",
        "TREND_UP",
        "TREND_UP",
        decision_time_ms=intent.decision_time_ms,
    )
    future = _evaluation(
        "TREND_DOWN",
        "TREND_DOWN",
        "TREND_DOWN",
        decision_time_ms=intent.decision_time_ms + 60_000,
    )

    baseline = attach_regime_preferences((intent,), (causal,))
    appended = attach_regime_preferences((intent,), (causal, future))

    assert appended == baseline
    assert appended[0].regime_decision_time_ms == intent.decision_time_ms


def test_unknown_canonical_context_keeps_a_lone_intent_ungated() -> None:
    """Warmup-incomplete evidence creates no preference and cannot block intent."""
    intent = _intent("long")
    unknown = _evaluation("UNKNOWN", "UNKNOWN", "UNKNOWN")

    assert attach_regime_preferences((intent,), (unknown,)) == (intent,)


def test_breakout_direction_uses_backend_structural_direction() -> None:
    """A BREAKOUT vote is directional only through causal backend structure."""
    evaluation = _evaluation(
        "BREAKOUT",
        "BREAKOUT",
        "TRANSITION",
        structural_direction="short",
    )

    weighted = attach_regime_preferences((_intent("short"),), (evaluation,))

    assert weighted[0].regime_alignment_score == pytest.approx(4.0 / 6.0)
    assert weighted[0].regime_alignment_stance == "directionally_supported"


def test_telemetry_only_canonical_identity_replaces_retired_range_provider() -> None:
    """The independent detector supplies routing context without a Range route."""
    evaluation = _evaluation(
        "TREND_DOWN",
        "TREND_DOWN",
        "RANGE",
        strategy_id="canonical_regime_telemetry_v1",
    )

    weighted = attach_regime_preferences((_intent("short"),), (evaluation,))

    assert weighted[0].regime_alignment_score == pytest.approx(4.0 / 6.0)
    assert weighted[0].regime_alignment_stance == "directionally_supported"


def _intent(side: str) -> StrategyIntent:
    return StrategyIntent(
        strategy_id="hulk_expansion_bidirectional_tuned_v2",
        symbol="BTC",
        side=side,
        decision_time_ms=1_785_600_000_000,
        reference_price=100.0,
        reason="fixture",
    )


def _evaluation(
    state_1m: str,
    state_5m: str,
    context_15m: str,
    *,
    structural_direction: str = "neutral",
    strategy_id: str = "range_onset_bidirectional_v1",
    decision_time_ms: int = 1_785_600_000_000,
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol="BTC",
        decision_time_ms=decision_time_ms,
        reference_price=100.0,
        decision_action="hold",
        eligible=False,
        reason="fixture",
        side=None,
        readiness=SignalReadiness(
            side=None,
            conditions_met=0,
            conditions_required=1,
            blockers=("fixture",),
            indicators=("FIXTURE",),
            metrics={"structural_direction": structural_direction},
        ),
        primary_regime=state_5m,
        state_1m=state_1m,
        state_5m=state_5m,
        context_15m=context_15m,
        confidence=0.7,
    )
