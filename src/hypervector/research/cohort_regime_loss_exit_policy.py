"""Causal report-only exit policy for opposed and adverse trade paths."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence

_MINUTE_MS = 60_000
_OPPOSITION_THRESHOLD = -0.5

RegimeLossExitState = Literal["triggered", "not_triggered"]


@dataclass(frozen=True)
class RegimeLossExitObservation:
    """One decision-time regime score with causal close and next-open prices."""

    decision_time_ms: int
    completed_close_price: float
    next_open_price: float
    structure_support_score: float | None

    def __post_init__(self) -> None:
        """Reject malformed or non-minute decision observations."""
        if (
            isinstance(self.decision_time_ms, bool)
            or not isinstance(self.decision_time_ms, int)
            or self.decision_time_ms < 0
            or self.decision_time_ms % _MINUTE_MS
        ):
            raise ValueError("loss-exit decision time must align to a minute")
        prices = (self.completed_close_price, self.next_open_price)
        if not all(math.isfinite(value) and value > 0.0 for value in prices):
            raise ValueError("loss-exit prices must be positive and finite")
        score = self.structure_support_score
        if score is not None and not math.isfinite(score):
            raise ValueError("loss-exit structure support must be finite")


@dataclass(frozen=True)
class RegimeLossExitResult:
    """One immutable challenger result without execution authority."""

    state: RegimeLossExitState
    reason: str
    trigger_decision_time_ms: int | None
    exit_reference_price: float | None
    trigger_close_return_bps: float | None
    consecutive_opposed_at_trigger: int | None
    maximum_consecutive_opposed: int
    current_consecutive_opposed: int
    unavailable_decisions: int
    coverage_gap_decisions: int
    worst_close_return_bps: float | None


def evaluate_regime_loss_exit(
    *,
    side: str,
    entry_price: float,
    observations: Sequence[RegimeLossExitObservation],
    loss_threshold_bps: float,
    persistence_decisions: int,
) -> RegimeLossExitResult:
    """Exit at the next open only when opposition and loss coexist causally."""
    direction = _direction(side)
    entry = _positive(entry_price, "loss-exit entry price")
    threshold = _positive(loss_threshold_bps, "loss-exit threshold bps")
    persistence = _positive_integer(
        persistence_decisions, "loss-exit persistence decisions"
    )
    _validate_order(observations)
    consecutive = 0
    maximum = 0
    unavailable = 0
    coverage_gaps = 0
    worst: float | None = None
    prior_decision_ms: int | None = None
    for observation in observations:
        if prior_decision_ms is not None:
            elapsed = observation.decision_time_ms - prior_decision_ms
            missing = elapsed // _MINUTE_MS - 1
            if missing:
                coverage_gaps += missing
                consecutive = 0
        prior_decision_ms = observation.decision_time_ms
        close_return = _directional_bps(
            direction, entry, observation.completed_close_price
        )
        worst = close_return if worst is None else min(worst, close_return)
        score = observation.structure_support_score
        if score is None:
            unavailable += 1
            consecutive = 0
            continue
        consecutive = consecutive + 1 if score <= _OPPOSITION_THRESHOLD else 0
        maximum = max(maximum, consecutive)
        if consecutive >= persistence and close_return <= -threshold:
            return RegimeLossExitResult(
                state="triggered",
                reason="persistent_opposition_adverse_close",
                trigger_decision_time_ms=observation.decision_time_ms,
                exit_reference_price=observation.next_open_price,
                trigger_close_return_bps=close_return,
                consecutive_opposed_at_trigger=consecutive,
                maximum_consecutive_opposed=maximum,
                current_consecutive_opposed=consecutive,
                unavailable_decisions=unavailable,
                coverage_gap_decisions=coverage_gaps,
                worst_close_return_bps=worst,
            )
    return RegimeLossExitResult(
        state="not_triggered",
        reason="conditions_not_jointly_satisfied",
        trigger_decision_time_ms=None,
        exit_reference_price=None,
        trigger_close_return_bps=None,
        consecutive_opposed_at_trigger=None,
        maximum_consecutive_opposed=maximum,
        current_consecutive_opposed=consecutive,
        unavailable_decisions=unavailable,
        coverage_gap_decisions=coverage_gaps,
        worst_close_return_bps=worst,
    )


def _direction(side: str) -> float:
    if side == "long":
        return 1.0
    if side == "short":
        return -1.0
    raise ValueError("loss-exit side must be long or short")


def _positive(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{label} must be positive and finite")
    return parsed


def _positive_integer(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _validate_order(observations: Sequence[RegimeLossExitObservation]) -> None:
    prior: int | None = None
    for observation in observations:
        if prior is not None and observation.decision_time_ms <= prior:
            raise ValueError("loss-exit decisions must be strictly increasing")
        prior = observation.decision_time_ms


def _directional_bps(direction: float, entry: float, price: float) -> float:
    return direction * (price - entry) / entry * 10_000.0
