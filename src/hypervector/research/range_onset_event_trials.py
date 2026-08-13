"""Frozen range-onset event-replay trial surfaces."""

from __future__ import annotations

from dataclasses import dataclass

_TRIALS = (
    (60.0, 0.10, 5.0),
    (60.0, 0.20, 15.0),
    (80.0, 0.10, 5.0),
    (80.0, 0.20, 15.0),
)
_CAPACITY_TRIALS = tuple((60.0, value, 5.0) for value in (0.02, 0.03, 0.05, 0.10))
_CAPACITY_SHAPE_TRIALS = tuple((value, 0.03, 5.0) for value in (60.0, 80.0))
_CAPACITY_SHAPE_MIDPOINT_TRIALS = tuple(
    (value, 0.03, 5.0) for value in (60.0, 70.0, 80.0)
)
_LATENCY_TRIALS = tuple(
    (stop_bps, 0.03, 5.0, delay_ms)
    for stop_bps in (60.0, 80.0)
    for delay_ms in (0, 8_000, 16_000)
)
_V49_TARGETS = (None, 25.0, 40.0, 60.0, 80.0, 120.0)


@dataclass(frozen=True)
class EventTrial:
    """One explicit account, exposure, stop, latency, and target hypothesis."""

    stop_bps: float
    margin_fraction: float
    leverage: float
    decision_delay_ms: int = 0
    target_bps: float | None = None
    initial_equity: float = 15_000.0
    taker_fee_rate: float = 0.00045

    @property
    def effective_exposure(self) -> float:
        """Return notional as a multiple of total portfolio equity."""
        return self.margin_fraction * self.leverage


def event_trial_grid() -> tuple[EventTrial, ...]:
    """Return the frozen two-shape, two-exposure event grid."""
    return tuple(EventTrial(*values) for values in _TRIALS)


def capacity_trial_grid() -> tuple[EventTrial, ...]:
    """Return the frozen low-notional finite-depth capacity ladder."""
    return tuple(EventTrial(*values) for values in _CAPACITY_TRIALS)


def capacity_shape_trial_grid() -> tuple[EventTrial, ...]:
    """Compare predeclared stops at the accepted 0.15x capacity."""
    return tuple(EventTrial(*values) for values in _CAPACITY_SHAPE_TRIALS)


def capacity_shape_midpoint_trial_grid() -> tuple[EventTrial, ...]:
    """Add a clearly post-hoc 70-bps midpoint at unchanged exposure."""
    return tuple(EventTrial(*values) for values in _CAPACITY_SHAPE_MIDPOINT_TRIALS)


def latency_trial_grid() -> tuple[EventTrial, ...]:
    """Return the preregistered stop-by-observed-delay robustness grid."""
    return tuple(EventTrial(*values) for values in _LATENCY_TRIALS)


def v49_target_trial_grid() -> tuple[EventTrial, ...]:
    """Return a post-hoc v49 SOL fixed-target challenger including its control."""
    return tuple(
        EventTrial(
            stop_bps=80.0,
            margin_fraction=0.15,
            leverage=5.0,
            target_bps=target,
            initial_equity=5_000.0,
            taker_fee_rate=0.000432,
        )
        for target in _V49_TARGETS
    )
