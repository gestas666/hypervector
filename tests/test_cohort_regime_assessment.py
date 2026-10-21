"""Causal open-position regime assessment tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_regime_assessment import build_regime_assessment


def test_weighted_assessment_separates_structure_from_component_alignment() -> None:
    """Structure support and component direction remain distinct evidence."""
    assessment = build_regime_assessment(
        "short",
        {
            "signal_provider": _context("TRANSITION"),
            "canonical_regime": _context(
                "TREND_DOWN",
                state_1m="TREND_UP",
                state_5m="TREND_DOWN",
                context_15m="TREND_DOWN",
                metrics={
                    "ema_21_55_direction": 1,
                    "sma_100_200_direction": -1,
                    "ema_11_34_direction": 1,
                    "harsi_direction": 1,
                    "mtf_5m_bias": 3,
                    "mtf_15m_bias": 1,
                    "trend_slope_bps": 0.5,
                },
            ),
        },
    )

    assert assessment["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "runtime_strategy_changed": False,
        "automatic_strategy_changes": False,
    }
    assert assessment["structure_support_score"] == pytest.approx(7.0 / 12.0)
    assert assessment["structure_stance"] == "directionally_supported"
    assert assessment["component_alignment_score"] == pytest.approx(-7.0 / 9.0)
    assert assessment["component_stance"] == "opposing_position"
    assert assessment["maximum_hold_context"] == "still_directionally_supported"


def test_assessment_retains_neutral_states_and_missing_components() -> None:
    """Range and transition evidence reduce support without inventing metrics."""
    assessment = build_regime_assessment(
        "long",
        {
            "signal_provider": _context("TRANSITION"),
            "canonical_regime": _context(
                "RANGE",
                state_1m="RANGE",
                state_5m="RANGE",
                context_15m="TREND_UP",
                confidence=0.7,
            ),
        },
    )

    assert assessment["structure_support_score"] == pytest.approx(2.0 / 12.0)
    assert assessment["structure_stance"] == "mixed_or_transition"
    assert assessment["component_alignment_score"] is None
    assert assessment["component_stance"] == "unavailable"
    assert assessment["movement_strength"] == pytest.approx(0.7)
    assert assessment["maximum_hold_context"] == "mixed_or_transition"


def test_assessment_rejects_invalid_side() -> None:
    """Only actual long and short lifecycle directions are accepted."""
    with pytest.raises(ValueError, match="side"):
        build_regime_assessment("flat", {})


def _context(
    primary: str,
    *,
    state_1m: str | None = None,
    state_5m: str | None = None,
    context_15m: str | None = None,
    confidence: float = 0.5,
    metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "observed",
        "primary_regime": primary,
        "state_1m": state_1m,
        "state_5m": state_5m,
        "context_15m": context_15m,
        "confidence": confidence,
        "readiness": {"metrics": metrics or {}},
    }
