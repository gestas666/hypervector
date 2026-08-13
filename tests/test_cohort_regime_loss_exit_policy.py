"""Tests for the report-only persistent-opposition loss-exit policy."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_regime_loss_exit_policy import (
    RegimeLossExitObservation,
    evaluate_regime_loss_exit,
)

_MINUTE_MS = 60_000


def _observation(
    minute: int,
    *,
    close: float,
    next_open: float,
    support: float | None = -1.0,
) -> RegimeLossExitObservation:
    return RegimeLossExitObservation(
        decision_time_ms=minute * _MINUTE_MS,
        completed_close_price=close,
        next_open_price=next_open,
        structure_support_score=support,
    )


def test_short_triggers_only_after_persistence_and_adverse_close() -> None:
    """A short exits at the next open after five opposed losing closes."""
    observations = tuple(
        _observation(minute, close=100.1, next_open=100.1) for minute in range(1, 5)
    ) + (_observation(5, close=100.35, next_open=100.4),)

    result = evaluate_regime_loss_exit(
        side="short",
        entry_price=100.0,
        observations=observations,
        loss_threshold_bps=30.0,
        persistence_decisions=5,
    )

    assert result.state == "triggered"
    assert result.reason == "persistent_opposition_adverse_close"
    assert result.trigger_decision_time_ms == 5 * _MINUTE_MS
    assert result.exit_reference_price == pytest.approx(100.4)
    assert result.trigger_close_return_bps == pytest.approx(-35.0)
    assert result.consecutive_opposed_at_trigger == 5


def test_long_path_is_symmetric() -> None:
    """A long uses falling closes and the next open without short-side leakage."""
    observations = tuple(
        _observation(minute, close=99.8, next_open=99.8) for minute in range(1, 5)
    ) + (_observation(5, close=99.6, next_open=99.55),)

    result = evaluate_regime_loss_exit(
        side="long",
        entry_price=100.0,
        observations=observations,
        loss_threshold_bps=30.0,
        persistence_decisions=5,
    )

    assert result.state == "triggered"
    assert result.exit_reference_price == pytest.approx(99.55)
    assert result.trigger_close_return_bps == pytest.approx(-40.0)


def test_nonopposed_decision_resets_persistence() -> None:
    """A transient regime recovery prevents an accumulated opposition exit."""
    observations = (
        *(_observation(minute, close=100.4, next_open=100.4) for minute in range(1, 5)),
        _observation(5, close=100.4, next_open=100.4, support=0.0),
        *(
            _observation(minute, close=100.4, next_open=100.4)
            for minute in range(6, 10)
        ),
    )

    result = evaluate_regime_loss_exit(
        side="short",
        entry_price=100.0,
        observations=observations,
        loss_threshold_bps=30.0,
        persistence_decisions=5,
    )

    assert result.state == "not_triggered"
    assert result.reason == "conditions_not_jointly_satisfied"
    assert result.maximum_consecutive_opposed == 4
    assert result.current_consecutive_opposed == 4


def test_missing_support_breaks_the_sequence_and_is_counted() -> None:
    """Unavailable regime evidence cannot be treated as supportive or opposed."""
    observations = (
        _observation(1, close=100.4, next_open=100.4),
        _observation(2, close=100.4, next_open=100.4, support=None),
        _observation(3, close=100.4, next_open=100.4),
    )

    result = evaluate_regime_loss_exit(
        side="short",
        entry_price=100.0,
        observations=observations,
        loss_threshold_bps=30.0,
        persistence_decisions=2,
    )

    assert result.state == "not_triggered"
    assert result.unavailable_decisions == 1
    assert result.maximum_consecutive_opposed == 1


def test_missing_minute_breaks_persistence_and_is_counted() -> None:
    """A timestamp gap cannot masquerade as consecutive completed decisions."""
    observations = (
        _observation(1, close=100.4, next_open=100.4),
        _observation(3, close=100.4, next_open=100.4),
    )

    result = evaluate_regime_loss_exit(
        side="short",
        entry_price=100.0,
        observations=observations,
        loss_threshold_bps=30.0,
        persistence_decisions=2,
    )

    assert result.state == "not_triggered"
    assert result.maximum_consecutive_opposed == 1
    assert result.coverage_gap_decisions == 1


def test_policy_rejects_out_of_order_decisions() -> None:
    """Noncausal ordering is an explicit technical error."""
    observations = (
        _observation(2, close=100.0, next_open=100.0),
        _observation(1, close=100.0, next_open=100.0),
    )

    with pytest.raises(ValueError, match="strictly increasing"):
        evaluate_regime_loss_exit(
            side="short",
            entry_price=100.0,
            observations=observations,
            loss_threshold_bps=30.0,
            persistence_decisions=2,
        )
