"""Report-only weighted regime context for open cohort positions."""

from __future__ import annotations

from collections.abc import Mapping
import math

from hypervector.research.cohort_live_audit_values import mapping

Record = Mapping[str, object]

_STRUCTURE_EVIDENCE = (
    ("signal_provider", "primary_regime", 3.0),
    ("canonical_regime", "primary_regime", 3.0),
    ("canonical_regime", "state_1m", 1.0),
    ("canonical_regime", "state_5m", 3.0),
    ("canonical_regime", "context_15m", 2.0),
)
_COMPONENT_EVIDENCE = (
    ("ema_21_55_direction", 1.0),
    ("sma_100_200_direction", 1.0),
    ("ema_11_34_direction", 1.0),
    ("harsi_direction", 1.0),
    ("mtf_5m_bias", 2.0),
    ("mtf_15m_bias", 2.0),
    ("trend_slope_bps", 1.0),
)
_STANCE_THRESHOLD = 0.5


def build_regime_assessment(side: str, current_context: Record) -> dict[str, object]:
    """Build a causal context score with no execution or model authority."""
    side_sign = _side_sign(side)
    structure_score, structure_weight = _structure_score(current_context, side_sign)
    component_score, component_weight = _component_score(current_context, side_sign)
    structure_stance = _stance(structure_score)
    return {
        "schema_version": 1,
        "mode": "causal_regime_context_challenger_v1",
        "contract": _contract(),
        "structure_support_score": structure_score,
        "structure_weight_observed": structure_weight,
        "structure_stance": structure_stance,
        "component_alignment_score": component_score,
        "component_weight_observed": component_weight,
        "component_stance": _component_stance(component_score),
        "movement_strength": _movement_strength(current_context),
        "maximum_hold_context": _maximum_hold_context(structure_stance),
        "limitations": _limitations(),
    }


def _side_sign(side: str) -> int:
    if side == "long":
        return 1
    if side == "short":
        return -1
    raise ValueError("regime assessment side must be long or short")


def _structure_score(contexts: Record, side_sign: int) -> tuple[float | None, float]:
    weighted = 0.0
    observed = 0.0
    for context_name, field, weight in _STRUCTURE_EVIDENCE:
        context = mapping(contexts.get(context_name), context_name)
        direction = _regime_direction(context.get(field), context)
        if direction is None:
            continue
        weighted += direction * side_sign * weight
        observed += weight
    return (None if observed == 0.0 else weighted / observed, observed)


def _regime_direction(value: object, context: Record) -> int | None:
    if context.get("status") != "observed" or value is None:
        return None
    if value == "TREND_UP":
        return 1
    if value == "TREND_DOWN":
        return -1
    if value in {"RANGE", "TRANSITION"}:
        return 0
    if value == "BREAKOUT":
        return _breakout_direction(context)
    raise ValueError(f"unsupported regime assessment state: {value}")


def _breakout_direction(context: Record) -> int:
    readiness = context.get("readiness")
    metrics = (
        mapping(readiness, "regime readiness").get("metrics") if readiness else None
    )
    if metrics is not None:
        structural = mapping(metrics, "regime readiness metrics").get(
            "structural_direction"
        )
        if structural in {"long", "short"}:
            return 1 if structural == "long" else -1
    side = context.get("side")
    return 1 if side == "long" else -1 if side == "short" else 0


def _component_score(contexts: Record, side_sign: int) -> tuple[float | None, float]:
    canonical = mapping(contexts.get("canonical_regime"), "canonical_regime")
    readiness = canonical.get("readiness")
    if readiness is None:
        return None, 0.0
    metrics_value = mapping(readiness, "canonical readiness").get("metrics")
    if metrics_value is None:
        return None, 0.0
    metrics = mapping(metrics_value, "canonical readiness metrics")
    weighted = 0.0
    observed = 0.0
    for name, weight in _COMPONENT_EVIDENCE:
        direction = _numeric_direction(metrics.get(name), name)
        if direction is None:
            continue
        weighted += direction * side_sign * weight
        observed += weight
    return (None if observed == 0.0 else weighted / observed, observed)


def _numeric_direction(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric when reported")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite when reported")
    return 1 if number > 0.0 else -1 if number < 0.0 else 0


def _movement_strength(contexts: Record) -> float | None:
    canonical = mapping(contexts.get("canonical_regime"), "canonical_regime")
    value = canonical.get("confidence")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("canonical confidence must be numeric when reported")
    strength = float(value)
    if not math.isfinite(strength) or not 0.0 <= strength <= 1.0:
        raise ValueError("canonical confidence must be within [0, 1]")
    return strength


def _stance(score: float | None) -> str:
    if score is None:
        return "unavailable"
    if score >= _STANCE_THRESHOLD:
        return "directionally_supported"
    if score <= -_STANCE_THRESHOLD:
        return "directionally_opposed"
    return "mixed_or_transition"


def _component_stance(score: float | None) -> str:
    stance = _stance(score)
    return {
        "directionally_supported": "aligned_with_position",
        "directionally_opposed": "opposing_position",
    }.get(stance, stance)


def _maximum_hold_context(structure_stance: str) -> str:
    return {
        "directionally_supported": "still_directionally_supported",
        "directionally_opposed": "directionally_opposed",
        "mixed_or_transition": "mixed_or_transition",
    }.get(structure_stance, "unavailable")


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }


def _limitations() -> list[str]:
    return [
        "weights encode timeframe hierarchy and are not fitted return forecasts",
        "component alignment is descriptive because later-window direction IC was inverse",
        "movement strength is regime confidence, not win probability",
        "maximum-hold context cannot submit, retain, or close a position",
    ]
