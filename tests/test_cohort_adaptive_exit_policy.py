"""Causal profit retention requirements, independent of venue and fitting."""

from dataclasses import replace

import pytest

from hypervector.live.cohort_adaptive_exit_policy import (
    AdaptiveExitObservation, AdaptiveExitState, advance_adaptive_exit,
)


def observation(**overrides: float | int | None) -> AdaptiveExitObservation:
    """Return a fresh supported-trend observation in bps-of-entry units."""
    return replace(AdaptiveExitObservation(60_000, 100.0, 15.0, 15.0, 1.0), **overrides)


def test_supported_trend_retains_room_and_floor_ratchets() -> None:
    """A healthy trend may retrace without undoing its profit protection."""
    first = advance_adaptive_exit(AdaptiveExitState(), observation())
    assert first.armed and first.floor_bps == 50.0 and first.exit_reason is None
    higher = advance_adaptive_exit(first, observation(observed_ms=75_000, pnl_bps=180.0))
    assert higher.floor_bps == 130.0
    assert advance_adaptive_exit(higher, observation(observed_ms=90_000, pnl_bps=150.0)).exit_reason is None
    crossed = advance_adaptive_exit(higher, observation(observed_ms=90_000, pnl_bps=125.0))
    assert crossed.exit_reason == "adaptive_profit_floor"


def test_opposed_regime_tightens_without_waiting_for_hours() -> None:
    """Identical profit paths produce less giveback under opposed regimes."""
    state = advance_adaptive_exit(AdaptiveExitState(), observation())
    opposed = advance_adaptive_exit(state, observation(observed_ms=75_000, pnl_bps=70.0, alignment=-1.0))
    assert opposed.floor_bps == 75.0
    assert opposed.exit_reason == "adaptive_profit_floor"


def test_volatility_costs_and_unknown_context_cannot_relax_floor() -> None:
    """Later uncertainty or volatility expansion cannot undo earned protection."""
    state = advance_adaptive_exit(AdaptiveExitState(), observation(alignment=-1.0))
    changed = advance_adaptive_exit(state, observation(observed_ms=75_000, pnl_bps=95.0, atr_bps=100.0, alignment=None))
    assert changed.floor_bps == state.floor_bps
    expensive = advance_adaptive_exit(AdaptiveExitState(), observation(pnl_bps=60.0, friction_bps=80.0))
    assert not expensive.armed


def test_book_requires_distinct_spaced_observations_and_corroboration() -> None:
    """A repeated timestamp or isolated imbalance cannot manufacture persistence."""
    state = AdaptiveExitState()
    for now, book_time in [(60_000, 60_000), (75_000, 60_000), (90_000, 90_000)]:
        state = advance_adaptive_exit(state, observation(observed_ms=now, pnl_bps=110.0, alignment=0.0, book_ms=book_time, signed_pressure=-.5))
    assert state.book_count == 2 and state.floor_bps == 75.0
    state = advance_adaptive_exit(state, observation(observed_ms=105_000, pnl_bps=85.0, alignment=0.0, book_ms=105_000, signed_pressure=-.5))
    assert state.book_count == 3 and state.floor_bps == 90.0
    assert state.exit_reason == "adaptive_profit_floor"


@pytest.mark.parametrize("book_ms", [1, 60_001])
def test_stale_and_future_books_do_not_count(book_ms: int) -> None:
    """Invalid temporal evidence is explicitly unavailable to the rule."""
    state = advance_adaptive_exit(AdaptiveExitState(), observation(book_ms=book_ms, signed_pressure=-1.0))
    assert state.book_count == 0


def test_duplicate_decision_is_idempotent_and_reverse_clock_rejected() -> None:
    """Replay cannot revise an already sampled observation or travel backwards."""
    state = advance_adaptive_exit(AdaptiveExitState(), observation())
    assert advance_adaptive_exit(state, observation(pnl_bps=0.0)) == state
    with pytest.raises(ValueError, match="backwards"):
        advance_adaptive_exit(state, observation(observed_ms=59_999))


@pytest.mark.parametrize("field,value", [("pnl_bps", float("nan")), ("atr_bps", -1.0), ("alignment", 2.0), ("friction_bps", -1.0)])
def test_invalid_numeric_evidence_rejected(field: str, value: float) -> None:
    """Non-finite and out-of-domain features must fail validation."""
    with pytest.raises(ValueError):
        advance_adaptive_exit(AdaptiveExitState(), observation(**{field: value}))
