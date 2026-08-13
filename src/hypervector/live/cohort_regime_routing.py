"""Causal regime preference for same-symbol provider routing conflicts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from hypervector.live.bidirectional_intents import (
    RegimeAlignmentStance,
    StrategyIntent,
)
from hypervector.live.canonical_regime_telemetry import (
    latest_canonical_evaluation_at_or_before,
)
from hypervector.live.multi_asset_signal_source import ProviderEvaluation

_ALIGNMENT_BASIS = "canonical_1m_5m_15m_1_3_2_v1"
_STATE_WEIGHTS = (("state_1m", 1.0), ("state_5m", 3.0), ("context_15m", 2.0))
_STANCE_THRESHOLD = 0.5


def attach_regime_preferences(
    intents: tuple[StrategyIntent, ...],
    evaluations: tuple[ProviderEvaluation, ...],
) -> tuple[StrategyIntent, ...]:
    """Attach latest causal canonical alignment without withholding any intent."""
    return tuple(
        _attach(
            intent,
            latest_canonical_evaluation_at_or_before(
                evaluations,
                intent.symbol,
                intent.decision_time_ms,
            ),
        )
        for intent in intents
    )


def routing_policy_payload() -> dict[str, object]:
    """Return the explicit non-gating conflict-ranking contract."""
    return {
        "mode": "same_symbol_conflict_preference_v1",
        "alignment_basis": _ALIGNMENT_BASIS,
        "state_weights": {field: weight for field, weight in _STATE_WEIGHTS},
        "standalone_intents_ungated": True,
        "forced_regime_exit": False,
        "fallback": "provider_priority_then_decision_time",
    }


def _attach(
    intent: StrategyIntent,
    evaluation: ProviderEvaluation | None,
) -> StrategyIntent:
    if evaluation is None:
        return intent
    score = _alignment_score(intent.side, evaluation)
    if score is None:
        return intent
    return replace(
        intent,
        regime_alignment_score=score,
        regime_alignment_stance=_stance(score),
        regime_decision_time_ms=evaluation.decision_time_ms,
        regime_alignment_basis=_ALIGNMENT_BASIS,
    )


def _alignment_score(side: str, evaluation: ProviderEvaluation) -> float | None:
    side_sign = 1 if side == "long" else -1
    weighted = 0.0
    observed = 0.0
    for field, weight in _STATE_WEIGHTS:
        direction = _state_direction(
            getattr(evaluation, field),
            evaluation.readiness.metrics,
        )
        if direction is None:
            continue
        weighted += direction * side_sign * weight
        observed += weight
    return None if observed == 0.0 else weighted / observed


def _state_direction(
    state: str | None,
    metrics: Mapping[str, object],
) -> int | None:
    if state is None:
        return None
    if state == "TREND_UP":
        return 1
    if state == "TREND_DOWN":
        return -1
    if state in {"RANGE", "TRANSITION"}:
        return 0
    if state == "UNKNOWN":
        return None
    if state == "BREAKOUT":
        structural = metrics.get("structural_direction")
        return 1 if structural == "long" else -1 if structural == "short" else 0
    raise ValueError(f"unsupported canonical regime state: {state}")


def _stance(score: float) -> RegimeAlignmentStance:
    if score >= _STANCE_THRESHOLD:
        return "directionally_supported"
    if score <= -_STANCE_THRESHOLD:
        return "directionally_opposed"
    return "mixed_or_transition"
