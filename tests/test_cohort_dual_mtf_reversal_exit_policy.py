"""Tests for the causal dual-timeframe profit-reversal exit policy."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_dual_mtf_reversal_exit_policy import (
    DualMtfReversalObservation,
    evaluate_dual_mtf_reversal_exit,
)

_MINUTE_MS = 60_000


def test_cost_clearance_cannot_trigger_on_the_same_decision() -> None:
    """A same-bar cost clear cannot establish earlier profitable state."""
    observations = (
        _observation(1, opposed=True, cleared_before=False),
        _observation(2, opposed=True, cleared_before=True),
    )

    result = evaluate_dual_mtf_reversal_exit(
        side="short", observations=observations, persistence_decisions=1
    )

    assert result.state == "triggered"
    assert result.trigger_decision_time_ms == 2 * _MINUTE_MS
    assert result.consecutive_opposed_at_trigger == 1


def test_both_timeframes_must_oppose_and_gaps_reset_persistence() -> None:
    """One-sided or discontinuous evidence cannot manufacture persistence."""
    observations = (
        _observation(1, directions=(1, 1)),
        _observation(2, directions=(1, 0)),
        _observation(4, directions=(1, 1)),
        _observation(5, directions=(1, 1)),
        _observation(6, directions=(1, 1)),
    )

    result = evaluate_dual_mtf_reversal_exit(
        side="short", observations=observations, persistence_decisions=3
    )

    assert result.state == "triggered"
    assert result.trigger_decision_time_ms == 6 * _MINUTE_MS
    assert result.maximum_consecutive_opposed == 3
    assert result.coverage_gap_decisions == 1


def test_missing_direction_is_counted_and_resets_opposition() -> None:
    """Unavailable directional evidence is visible and fails closed."""
    result = evaluate_dual_mtf_reversal_exit(
        side="long",
        observations=(
            _observation(1, directions=(-1, -1)),
            _observation(2, directions=(None, -1)),
        ),
        persistence_decisions=2,
    )

    assert result.state == "not_triggered"
    assert result.unavailable_decisions == 1
    assert result.maximum_consecutive_opposed == 1


def test_policy_rejects_non_chronological_observations() -> None:
    """Duplicate decision boundaries cannot be silently deduplicated."""
    with pytest.raises(ValueError, match="strictly increasing"):
        evaluate_dual_mtf_reversal_exit(
            side="long",
            observations=(_observation(1), _observation(1)),
            persistence_decisions=1,
        )


def _observation(
    minute: int,
    *,
    opposed: bool = False,
    cleared_before: bool = True,
    directions: tuple[int | None, int | None] | None = None,
) -> DualMtfReversalObservation:
    direction_1m, direction_5m = directions or ((1, 1) if opposed else (-1, -1))
    return DualMtfReversalObservation(
        decision_time_ms=minute * _MINUTE_MS,
        completed_close_price=100.0,
        next_open_price=100.1,
        direction_1m=direction_1m,
        direction_5m=direction_5m,
        cost_cleared_before_decision=cleared_before,
        estimated_net_at_completed_close_usd=0.2 if cleared_before else -0.1,
    )
