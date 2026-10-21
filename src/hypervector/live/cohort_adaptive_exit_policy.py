"""Causal profit-retention exit mechanisms; values are bps of entry, not leverage ROE.

Two mechanisms exist. Neither carries tuned values: every threshold comes from
the provider's execution contract in the profile.

* ``regime_book_profit_retention`` arms a monotone floor once the peak clears an
  activation (the larger of a minimum, an ATR multiple and friction plus a net
  buffer) and lets the peak give back an allowance that depends on canonical
  regime alignment and confirmed opposing book pressure.
* ``regime_flip_floor_retention`` works in units of the lifecycle's own initial
  stop distance (R): a profit floor arms after a peak of ``floor_activation_r``
  and a regime-flip ratchet exits on a giveback of ``giveback_r`` once the
  alignment turns opposed. Its break-even venue stop raise uses
  ``breakeven_offset_bps``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
import math

ADAPTIVE_EXIT_POLICY = "regime_book_profit_retention"
RETENTION_EXIT_POLICY = "regime_flip_floor_retention"
ADAPTIVE_EXIT_POLICIES = frozenset(
    {"none", ADAPTIVE_EXIT_POLICY, RETENTION_EXIT_POLICY}
)
PROFIT_FLOOR_EXIT = "profit_floor"
REGIME_FLIP_EXIT = "regime_flip_giveback"
RETENTION_EXIT_REASONS = frozenset({PROFIT_FLOOR_EXIT, REGIME_FLIP_EXIT})
# Freshness bounds of the causal top-of-book input (technical, not tuning).
BOOK_MAX_AGE_MS = 30_000
BOOK_MIN_SPACING_MS = 10_000
BOOK_MAX_SPACING_MS = 45_000
MAXIMUM_BOOK_CONFIRMATIONS = 10


@dataclass(frozen=True)
class AdaptiveExitParameters:
    """Profile values of the regime/book profit-retention floor.

    Each giveback allowance is ``max(<name>_allowance_bps, <name>_allowance_atr
    * ATR)`` and is chosen, in order, for supported alignment
    (``alignment >= regime_support``), confirmed opposing book pressure,
    opposed alignment (``alignment <= -regime_support``), or otherwise default.
    """

    minimum_activation_bps: float
    activation_atr_multiple: float
    net_buffer_bps: float
    maximum_giveback_fraction: float
    regime_support: float
    opposing_pressure: float
    book_confirmations: int
    supported_allowance_bps: float
    supported_allowance_atr: float
    confirmed_allowance_bps: float
    confirmed_allowance_atr: float
    opposed_allowance_bps: float
    opposed_allowance_atr: float
    default_allowance_bps: float
    default_allowance_atr: float

    def __post_init__(self) -> None:
        """Reject values that could not bound a monotone floor."""
        for item in fields(self):
            if item.name == "book_confirmations":
                continue
            _finite(getattr(self, item.name), item.name)
            object.__setattr__(self, item.name, float(getattr(self, item.name)))
        for name in (
            "minimum_activation_bps",
            "activation_atr_multiple",
            "net_buffer_bps",
            "supported_allowance_bps",
            "supported_allowance_atr",
            "confirmed_allowance_bps",
            "confirmed_allowance_atr",
            "opposed_allowance_bps",
            "opposed_allowance_atr",
            "default_allowance_bps",
            "default_allowance_atr",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"adaptive exit {name} must be nonnegative")
        if not 0 < self.maximum_giveback_fraction <= 1:
            raise ValueError("adaptive exit maximum_giveback_fraction must be in (0, 1]")
        if not 0 < self.regime_support <= 1:
            raise ValueError("adaptive exit regime_support must be in (0, 1]")
        if not -1 <= self.opposing_pressure < 0:
            raise ValueError("adaptive exit opposing_pressure must be in [-1, 0)")
        count = self.book_confirmations
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= MAXIMUM_BOOK_CONFIRMATIONS
        ):
            raise ValueError(
                "adaptive exit book_confirmations must be an integer in "
                f"[1, {MAXIMUM_BOOK_CONFIRMATIONS}]"
            )

    @classmethod
    def from_payload(cls, value: object) -> AdaptiveExitParameters | None:
        """Parse an explicit optional table without inventing defaults."""
        return _parameters_from_payload(cls, value, "adaptive_exit")

    def as_payload(self) -> dict[str, object]:
        """Return the exact JSON-safe parameter table."""
        return asdict(self)


@dataclass(frozen=True)
class RetentionExitParameters:
    """Profile values of the regime-flip ratchet and profit floor, in R units."""

    activation_r: float
    giveback_r: float
    opposed_alignment: float
    floor_activation_r: float
    floor_r: float
    breakeven_offset_bps: float

    def __post_init__(self) -> None:
        """Reject values that could not bound a floor or a giveback."""
        for item in fields(self):
            _finite(getattr(self, item.name), item.name)
            object.__setattr__(self, item.name, float(getattr(self, item.name)))
        for name in ("activation_r", "giveback_r", "floor_activation_r", "floor_r"):
            if getattr(self, name) <= 0:
                raise ValueError(f"retention exit {name} must be positive")
        if self.floor_r >= self.floor_activation_r:
            raise ValueError("retention exit floor_r must be below floor_activation_r")
        if not -1 <= self.opposed_alignment < 0:
            raise ValueError("retention exit opposed_alignment must be in [-1, 0)")
        if self.breakeven_offset_bps < 0:
            raise ValueError("retention exit breakeven_offset_bps must be nonnegative")

    @classmethod
    def from_payload(cls, value: object) -> RetentionExitParameters | None:
        """Parse an explicit optional table without inventing defaults."""
        return _parameters_from_payload(cls, value, "retention_exit")

    def as_payload(self) -> dict[str, object]:
        """Return the exact JSON-safe parameter table."""
        return asdict(self)


def _parameters_from_payload(cls: type, value: object, label: str) -> object:
    if value is None:
        return None
    if isinstance(value, cls):
        return value
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a table")
    names = {item.name for item in fields(cls)}
    unknown = sorted(str(key) for key in value if key not in names)
    missing = sorted(name for name in names if name not in value)
    if unknown or missing:
        raise ValueError(
            f"{label} keys are invalid: unknown={unknown}, missing={missing}"
        )
    return cls(**{name: value[name] for name in names})


def _finite(value: object, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"exit parameter {label} must be finite numeric")


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
    parameters: AdaptiveExitParameters,
) -> AdaptiveExitState:
    """Advance a monotone floor once; future observations cannot revise an exit."""
    if observation.observed_ms < previous.observed_ms:
        raise ValueError("adaptive exit clock moved backwards")
    if (
        observation.observed_ms == previous.observed_ms
        or previous.exit_reason is not None
    ):
        return previous
    state = _advance_book(previous, observation, parameters)
    peak = max(previous.peak_bps, observation.pnl_bps)
    activation = max(
        parameters.minimum_activation_bps,
        parameters.activation_atr_multiple * observation.atr_bps,
        observation.friction_bps + parameters.net_buffer_bps,
    )
    armed = previous.armed or peak >= activation
    floor = previous.floor_bps
    if armed:
        allowance = _allowance(observation, state.book_count, parameters)
        floor = max(
            observation.friction_bps + parameters.net_buffer_bps,
            peak - min(allowance, parameters.maximum_giveback_fraction * peak),
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


def _allowance(
    observation: AdaptiveExitObservation,
    book_count: int,
    parameters: AdaptiveExitParameters,
) -> float:
    alignment, atr = observation.alignment, observation.atr_bps
    if alignment is not None and alignment >= parameters.regime_support:
        return max(
            parameters.supported_allowance_bps,
            parameters.supported_allowance_atr * atr,
        )
    if alignment is not None and book_count >= parameters.book_confirmations:
        return max(
            parameters.confirmed_allowance_bps,
            parameters.confirmed_allowance_atr * atr,
        )
    if alignment is not None and alignment <= -parameters.regime_support:
        return max(
            parameters.opposed_allowance_bps,
            parameters.opposed_allowance_atr * atr,
        )
    return max(
        parameters.default_allowance_bps,
        parameters.default_allowance_atr * atr,
    )


def _advance_book(
    previous: AdaptiveExitState,
    observation: AdaptiveExitObservation,
    parameters: AdaptiveExitParameters,
) -> AdaptiveExitState:
    stamp, pressure = observation.book_ms, observation.signed_pressure
    if stamp is None or not 0 <= observation.observed_ms - stamp <= BOOK_MAX_AGE_MS:
        return replace(previous, book_count=0, book_ms=None)
    if previous.book_ms == stamp:
        return previous
    if previous.book_ms is not None and stamp < previous.book_ms:
        return replace(previous, book_count=0)
    if pressure is None or pressure > parameters.opposing_pressure:
        return replace(previous, book_count=0, book_ms=stamp)
    delta = stamp - previous.book_ms if previous.book_ms is not None else None
    if delta is not None and 0 < delta < BOOK_MIN_SPACING_MS:
        return previous
    count = (
        previous.book_count + 1
        if delta is not None and delta <= BOOK_MAX_SPACING_MS
        else 1
    )
    return replace(
        previous,
        book_count=min(parameters.book_confirmations, count),
        book_ms=stamp,
    )


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
    """Restart-persistent state for exactly one open lifecycle; every field is monotone."""

    observed_ms: int = 0
    peak_bps: float = 0.0
    armed: bool = False
    floor_armed: bool = False
    floor_bps: float | None = None
    exit_reason: str | None = None


def advance_retention_exit(
    previous: RetentionExitState,
    observation: RetentionExitObservation,
    parameters: RetentionExitParameters,
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
    armed = previous.armed or peak >= parameters.activation_r * risk
    floor_armed = (
        previous.floor_armed or peak >= parameters.floor_activation_r * risk
    )
    floor = previous.floor_bps
    if floor_armed:
        floor = max(parameters.floor_r * risk, floor if floor is not None else 0.0)
    reason = None
    if floor is not None and observation.pnl_bps <= floor:
        reason = PROFIT_FLOOR_EXIT
    elif (
        armed
        and observation.alignment is not None
        and observation.alignment <= parameters.opposed_alignment
        and observation.pnl_bps <= peak - parameters.giveback_r * risk
    ):
        reason = REGIME_FLIP_EXIT
    return RetentionExitState(
        observation.observed_ms, peak, armed, floor_armed, floor, reason
    )
