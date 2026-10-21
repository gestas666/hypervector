"""Regime-flip ratchet and profit-floor retention policy contracts."""

import math

import pytest

from hypervector.live.cohort_adaptive_exit_policy import (
    ADAPTIVE_EXIT_POLICIES,
    ADAPTIVE_EXIT_POLICY,
    RETENTION_EXIT_POLICY,
    RetentionExitObservation,
    RetentionExitParameters,
    RetentionExitState,
    advance_retention_exit as _advance,
)

from exit_parameter_fixtures import RETENTION_PARAMETERS


def advance_retention_exit(
    state: RetentionExitState, observation: RetentionExitObservation
) -> RetentionExitState:
    return _advance(state, observation, RETENTION_PARAMETERS)


def _obs(ms: int, pnl: float, alignment: float | None = None, risk: float = 100.0):
    return RetentionExitObservation(
        observed_ms=ms, pnl_bps=pnl, risk_bps=risk, alignment=alignment
    )


def test_registry_holds_exactly_the_supported_names() -> None:
    assert RETENTION_EXIT_POLICY == "regime_flip_floor_retention"
    assert ADAPTIVE_EXIT_POLICIES == frozenset(
        {"none", ADAPTIVE_EXIT_POLICY, RETENTION_EXIT_POLICY}
    )


def test_arms_at_half_risk_and_floors_at_two_risk() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 49.9))
    assert not state.armed and state.peak_bps == 49.9 and state.floor_bps is None
    state = advance_retention_exit(state, _obs(2_000, 50.0))
    assert state.armed and not state.floor_armed and state.floor_bps is None
    state = advance_retention_exit(state, _obs(3_000, 200.0))
    assert state.floor_armed and state.floor_bps == 50.0 and state.exit_reason is None


def test_losing_path_never_arms_or_exits() -> None:
    state = RetentionExitState()
    for ms, pnl in ((1_000, -10.0), (2_000, -80.0), (3_000, 20.0), (4_000, -99.0)):
        state = advance_retention_exit(state, _obs(ms, pnl, alignment=-1.0))
    assert not state.armed and state.floor_bps is None and state.exit_reason is None
    assert state.peak_bps == 20.0


def test_regime_flip_requires_known_opposed_alignment() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 120.0))
    state = advance_retention_exit(state, _obs(2_000, 40.0, alignment=None))
    assert state.exit_reason is None
    state = advance_retention_exit(state, _obs(3_000, 40.0, alignment=0.7))
    assert state.exit_reason is None
    state = advance_retention_exit(state, _obs(4_000, 40.0, alignment=-0.4))
    assert state.exit_reason is None
    state = advance_retention_exit(state, _obs(5_000, 40.0, alignment=-0.5))
    assert state.exit_reason == "regime_flip_giveback"


def test_regime_flip_needs_half_risk_giveback_from_peak() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 120.0))
    state = advance_retention_exit(state, _obs(2_000, 71.0, alignment=-1.0))
    assert state.exit_reason is None
    state = advance_retention_exit(state, _obs(3_000, 70.0, alignment=-1.0))
    assert state.exit_reason == "regime_flip_giveback"


def test_arming_observation_itself_cannot_exit() -> None:
    state = advance_retention_exit(
        RetentionExitState(), _obs(1_000, 250.0, alignment=-1.0)
    )
    assert state.armed and state.floor_armed and state.exit_reason is None


def test_profit_floor_exit_takes_precedence_over_regime_flip() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 250.0))
    held = advance_retention_exit(state, _obs(2_000, 60.0, alignment=None))
    assert held.exit_reason is None
    flipped = advance_retention_exit(state, _obs(2_000, 60.0, alignment=-1.0))
    assert flipped.exit_reason == "regime_flip_giveback"
    floored = advance_retention_exit(state, _obs(2_000, 50.0, alignment=-1.0))
    assert floored.exit_reason == "profit_floor"
    unknown = advance_retention_exit(state, _obs(2_000, 49.0, alignment=None))
    assert unknown.exit_reason == "profit_floor"


def test_exit_is_terminal_same_stamp_idempotent_and_clock_monotone() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 250.0))
    exited = advance_retention_exit(state, _obs(2_000, 40.0))
    assert exited.exit_reason == "profit_floor"
    assert advance_retention_exit(exited, _obs(2_000, 300.0)) == exited
    assert advance_retention_exit(exited, _obs(3_000, 300.0)) == exited
    with pytest.raises(ValueError):
        advance_retention_exit(exited, _obs(1_500, 300.0))


def test_state_is_monotone_even_if_risk_input_shrinks() -> None:
    state = advance_retention_exit(RetentionExitState(), _obs(1_000, 250.0, risk=100.0))
    later = advance_retention_exit(state, _obs(2_000, 240.0, risk=60.0))
    assert later.floor_bps == 50.0 and later.armed and later.floor_armed
    assert later.peak_bps == 250.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pnl_bps": math.nan},
        {"pnl_bps": math.inf},
        {"risk_bps": 0.0},
        {"risk_bps": -5.0},
        {"risk_bps": math.nan},
        {"alignment": 1.5},
        {"alignment": math.nan},
        {"observed_ms": 0},
        {"observed_ms": True},
    ],
)
def test_invalid_observation_is_refused(kwargs: dict[str, object]) -> None:
    base = {"observed_ms": 1_000, "pnl_bps": 10.0, "risk_bps": 100.0, "alignment": None}
    with pytest.raises(ValueError):
        RetentionExitObservation(**{**base, **kwargs})


def test_profile_parameters_drive_the_ratchet_and_floor() -> None:
    """Different profile values move activation, floor and giveback accordingly."""
    wide = RetentionExitParameters(
        activation_r=1.0,
        giveback_r=1.0,
        opposed_alignment=-0.9,
        floor_activation_r=3.0,
        floor_r=1.0,
        breakeven_offset_bps=10.0,
    )
    state = _advance(RetentionExitState(), _obs(1_000, 99.0), wide)
    assert not state.armed
    state = _advance(state, _obs(2_000, 300.0), wide)
    assert state.armed and state.floor_armed and state.floor_bps == 100.0
    held = _advance(state, _obs(3_000, 201.0, alignment=-0.5), wide)
    assert held.exit_reason is None
    flipped = _advance(state, _obs(3_000, 200.0, alignment=-0.9), wide)
    assert flipped.exit_reason == "regime_flip_giveback"


@pytest.mark.parametrize(
    "overrides",
    [
        {"activation_r": 0.0},
        {"giveback_r": -1.0},
        {"floor_r": 2.0},
        {"opposed_alignment": 0.1},
        {"breakeven_offset_bps": -1.0},
        {"floor_activation_r": math.nan},
    ],
)
def test_retention_parameters_reject_unusable_values(overrides: dict) -> None:
    values = {
        "activation_r": 0.5,
        "giveback_r": 0.5,
        "opposed_alignment": -0.5,
        "floor_activation_r": 2.0,
        "floor_r": 0.5,
        "breakeven_offset_bps": 25.0,
        **overrides,
    }
    with pytest.raises(ValueError):
        RetentionExitParameters(**values)


def test_retention_parameters_parse_strictly_from_a_profile_table() -> None:
    table = RETENTION_PARAMETERS.as_payload()
    assert RetentionExitParameters.from_payload(table) == RETENTION_PARAMETERS
    assert RetentionExitParameters.from_payload(None) is None
    with pytest.raises(ValueError, match="finite"):
        RetentionExitParameters.from_payload({**table, "floor_r": None})
    partial = dict(table)
    partial.pop("floor_r")
    with pytest.raises(ValueError, match="missing"):
        RetentionExitParameters.from_payload(partial)
    with pytest.raises(ValueError, match="unknown"):
        RetentionExitParameters.from_payload({**table, "extra": 1.0})
