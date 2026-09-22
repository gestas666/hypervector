"""Versioned causal profit retention; values are bps of entry, not leverage ROE."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

ADAPTIVE_EXIT_POLICY = "regime_book_profit_retention_v1"
RETENTION_EXIT_POLICY = "regime_flip_floor_retention_v2"
ADAPTIVE_EXIT_POLICIES = frozenset(
    {"none", ADAPTIVE_EXIT_POLICY, RETENTION_EXIT_POLICY}
)
# v2 constants in units of the lifecycle's own initial stop distance (R).
ACTIVATION_R = 0.5
GIVEBACK_R = 0.5
OPPOSED_ALIGNMENT = -0.5
FLOOR_ACTIVATION_R = 2.0
FLOOR_R = 0.5
BREAKEVEN_BPS = 25.0
PROFIT_FLOOR_EXIT = "profit_floor"
REGIME_FLIP_EXIT = "regime_flip_giveback"
RETENTION_EXIT_REASONS = frozenset({PROFIT_FLOOR_EXIT, REGIME_FLIP_EXIT})
BOOK_MAX_AGE_MS = 30_000
BOOK_MIN_SPACING_MS = 10_000
BOOK_MAX_SPACING_MS = 45_000
BOOK_CONFIRMATIONS = 3
OPPOSING_PRESSURE = -0.35
REGIME_SUPPORT = 0.5
MIN_ACTIVATION_BPS = 60.0
NET_BUFFER_BPS = 20.0
MAX_GIVEBACK_FRACTION = 0.5


@dataclass(frozen=True)
class AdaptiveExitObservation:
    """One causal liquidation mark and explicitly available context."""

    observed_ms: int
    pnl_bps: float
    atr_bps: float
    friction_bps: float
    alignment: float | None
    book_ms: int | None = None
    signed_pressure: float | None = None

    def __post_init__(self) -> None:
        """Reject invalid numerical evidence before it can influence a floor."""
        values = (self.pnl_bps, self.atr_bps, self.friction_bps)
        if any(isinstance(value, bool) or not math.isfinite(value) for value in values):
            raise ValueError("adaptive exit values must be finite numbers")
        if self.atr_bps < 0 or self.friction_bps < 0:
            raise ValueError("adaptive volatility and friction must be nonnegative")
        if (
            isinstance(self.observed_ms, bool)
            or not isinstance(self.observed_ms, int)
            or self.observed_ms <= 0
        ):
            raise ValueError("adaptive observed_ms must be a positive integer")
        for value in (self.alignment, self.signed_pressure):
            if value is not None and (not math.isfinite(value) or not -1 <= value <= 1):
                raise ValueError("adaptive context must be finite and within [-1, 1]")


@dataclass(frozen=True)
class AdaptiveExitState:
    """Restart-persistent state for exactly one open lifecycle."""

    observed_ms: int = 0
    peak_bps: float = 0.0
    armed: bool = False
    floor_bps: float | None = None
    book_ms: int | None = None
    book_count: int = 0
    exit_reason: str | None = None


def advance_adaptive_exit(
    previous: AdaptiveExitState,
    observation: AdaptiveExitObservation,
) -> AdaptiveExitState:
    """Advance a monotone floor once; future observations cannot revise an exit."""
    if observation.observed_ms < previous.observed_ms:
        raise ValueError("adaptive exit clock moved backwards")
    if (
        observation.observed_ms == previous.observed_ms
        or previous.exit_reason is not None
    ):
        return previous
    state = _advance_book(previous, observation)
    peak = max(previous.peak_bps, observation.pnl_bps)
    activation = max(
        MIN_ACTIVATION_BPS,
        2 * observation.atr_bps,
        observation.friction_bps + NET_BUFFER_BPS,
    )
    armed = previous.armed or peak >= activation
    floor = previous.floor_bps
    if armed:
        allowance = _allowance(observation, state.book_count)
        floor = max(
            observation.friction_bps + NET_BUFFER_BPS,
            peak - min(allowance, MAX_GIVEBACK_FRACTION * peak),
            floor if floor is not None else 0.0,
        )
    reason = (
        "adaptive_profit_floor"
        if floor is not None and observation.pnl_bps <= floor
        else None
    )
    return replace(
        state,
        observed_ms=observation.observed_ms,
        peak_bps=peak,
        armed=armed,
        floor_bps=floor,
        exit_reason=reason,
    )


def _allowance(observation: AdaptiveExitObservation, book_count: int) -> float:
    alignment, atr = observation.alignment, observation.atr_bps
    if alignment is not None and alignment >= REGIME_SUPPORT:
        return max(50.0, 3 * atr)
    if alignment is not None and book_count >= BOOK_CONFIRMATIONS:
        return max(20.0, atr)
    if alignment is not None and alignment <= -REGIME_SUPPORT:
        return max(25.0, atr)
    return max(35.0, 2 * atr)


def _advance_book(
    previous: AdaptiveExitState,
    observation: AdaptiveExitObservation,
) -> AdaptiveExitState:
    stamp, pressure = observation.book_ms, observation.signed_pressure
    if stamp is None or not 0 <= observation.observed_ms - stamp <= BOOK_MAX_AGE_MS:
        return replace(previous, book_count=0, book_ms=None)
    if previous.book_ms == stamp:
        return previous
    if previous.book_ms is not None and stamp < previous.book_ms:
        return replace(previous, book_count=0)
    if pressure is None or pressure > OPPOSING_PRESSURE:
        return replace(previous, book_count=0, book_ms=stamp)
    delta = stamp - previous.book_ms if previous.book_ms is not None else None
    if delta is not None and 0 < delta < BOOK_MIN_SPACING_MS:
        return previous
    count = (
        previous.book_count + 1
        if delta is not None and delta <= BOOK_MAX_SPACING_MS
        else 1
    )
    return replace(previous, book_count=min(BOOK_CONFIRMATIONS, count), book_ms=stamp)


@dataclass(frozen=True)
class RetentionExitObservation:
    """One executable-quote mark in bps of entry, with the lifecycle's own risk unit."""

    observed_ms: int
    pnl_bps: float
    risk_bps: float
    alignment: float | None = None

    def __post_init__(self) -> None:
        """Reject evidence that cannot bound a floor or a giveback."""
        for value in (self.pnl_bps, self.risk_bps):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("retention exit values must be finite numbers")
        if self.risk_bps <= 0:
            raise ValueError("retention exit risk unit must be positive")
        if (
            isinstance(self.observed_ms, bool)
            or not isinstance(self.observed_ms, int)
            or self.observed_ms <= 0
        ):
            raise ValueError("retention observed_ms must be a positive integer")
        alignment = self.alignment
        if alignment is not None and (
            isinstance(alignment, bool)
            or not math.isfinite(alignment)
            or not -1 <= alignment <= 1
        ):
            raise ValueError("retention alignment must be finite and within [-1, 1]")


@dataclass(frozen=True)
class RetentionExitState:
    """Restart-persistent v2 state for exactly one open lifecycle; every field is monotone."""

    observed_ms: int = 0
    peak_bps: float = 0.0
    armed: bool = False
    floor_armed: bool = False
    floor_bps: float | None = None
    exit_reason: str | None = None


def advance_retention_exit(
    previous: RetentionExitState,
    observation: RetentionExitObservation,
) -> RetentionExitState:
    """Advance the regime-flip ratchet and profit floor once; exits are terminal."""
    if observation.observed_ms < previous.observed_ms:
        raise ValueError("retention exit clock moved backwards")
    if (
        observation.observed_ms == previous.observed_ms
        or previous.exit_reason is not None
    ):
        return previous
    risk = observation.risk_bps
    peak = max(previous.peak_bps, observation.pnl_bps)
    armed = previous.armed or peak >= ACTIVATION_R * risk
    floor_armed = previous.floor_armed or peak >= FLOOR_ACTIVATION_R * risk
    floor = previous.floor_bps
    if floor_armed:
        floor = max(FLOOR_R * risk, floor if floor is not None else 0.0)
    reason = None
    if floor is not None and observation.pnl_bps <= floor:
        reason = PROFIT_FLOOR_EXIT
    elif (
        armed
        and observation.alignment is not None
        and observation.alignment <= OPPOSED_ALIGNMENT
        and observation.pnl_bps <= peak - GIVEBACK_R * risk
    ):
        reason = REGIME_FLIP_EXIT
    return RetentionExitState(
        observation.observed_ms, peak, armed, floor_armed, floor, reason
    )
