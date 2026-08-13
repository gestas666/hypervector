"""Causal dual-timeframe reversal exits after prior cost clearance."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence

_MINUTE_MS = 60_000

DualMtfExitState = Literal["triggered", "not_triggered"]


@dataclass(frozen=True)
class DualMtfReversalObservation:
    """One completed-state decision with a causal next-open reference."""

    decision_time_ms: int
    completed_close_price: float
    next_open_price: float
    direction_1m: int | None
    direction_5m: int | None
    cost_cleared_before_decision: bool
    estimated_net_at_completed_close_usd: float

    def __post_init__(self) -> None:
        """Reject malformed decision, price, direction, and cost evidence."""
        _validate_timestamp(self.decision_time_ms)
        _validate_prices(self.completed_close_price, self.next_open_price)
        if self.direction_1m not in {-1, 0, 1, None}:
            raise ValueError("1m reversal direction is invalid")
        if self.direction_5m not in {-1, 0, 1, None}:
            raise ValueError("5m reversal direction is invalid")
        if not isinstance(self.cost_cleared_before_decision, bool):
            raise TypeError("cost-cleared state must be boolean")
        if not math.isfinite(self.estimated_net_at_completed_close_usd):
            raise ValueError("completed-close net estimate must be finite")


@dataclass(frozen=True)
class DualMtfReversalExitResult:
    """First causal trigger and full coverage diagnostics for one lifecycle."""

    state: DualMtfExitState
    reason: str
    trigger_decision_time_ms: int | None
    exit_reference_price: float | None
    consecutive_opposed_at_trigger: int | None
    maximum_consecutive_opposed: int
    current_consecutive_opposed: int
    unavailable_decisions: int
    coverage_gap_decisions: int
    cost_cleared_decisions: int


def evaluate_dual_mtf_reversal_exit(
    *,
    side: str,
    observations: Sequence[DualMtfReversalObservation],
    persistence_decisions: int,
) -> DualMtfReversalExitResult:
    """Exit next-open after prior cost clearance and persistent 1m+5m opposition."""
    side_sign = _side_sign(side)
    persistence = _positive_integer(persistence_decisions)
    _require_chronology(observations)
    state = _EvaluationState()
    prior_ms: int | None = None
    for row in observations:
        state.add_gap(prior_ms, row.decision_time_ms)
        prior_ms = row.decision_time_ms
        state.observe(row, side_sign)
        if state.consecutive >= persistence:
            return state.triggered(row)
    return state.not_triggered()


@dataclass
class _EvaluationState:
    consecutive: int = 0
    maximum: int = 0
    unavailable: int = 0
    gaps: int = 0
    cleared: int = 0

    def add_gap(self, prior_ms: int | None, current_ms: int) -> None:
        """Count missing decisions and reset state across discontinuities."""
        if prior_ms is None:
            return
        missing = (current_ms - prior_ms) // _MINUTE_MS - 1
        if missing:
            self.gaps += missing
            self.consecutive = 0

    def observe(self, row: DualMtfReversalObservation, side_sign: int) -> None:
        """Advance the conjunction using only previously cleared cost state."""
        self.cleared += int(row.cost_cleared_before_decision)
        directions = (row.direction_1m, row.direction_5m)
        if None in directions:
            self.unavailable += 1
            self.consecutive = 0
            return
        opposed = all(value == -side_sign for value in directions)
        self.consecutive = (
            self.consecutive + 1 if opposed and row.cost_cleared_before_decision else 0
        )
        self.maximum = max(self.maximum, self.consecutive)

    def triggered(self, row: DualMtfReversalObservation) -> DualMtfReversalExitResult:
        """Build a triggered result at the row's causal execution boundary."""
        return DualMtfReversalExitResult(
            "triggered",
            "prior_cost_clearance_and_dual_mtf_opposition",
            row.decision_time_ms,
            row.next_open_price,
            self.consecutive,
            self.maximum,
            self.consecutive,
            self.unavailable,
            self.gaps,
            self.cleared,
        )

    def not_triggered(self) -> DualMtfReversalExitResult:
        """Build a complete non-trigger result without dropping the lifecycle."""
        return DualMtfReversalExitResult(
            "not_triggered",
            "conditions_not_jointly_satisfied",
            None,
            None,
            None,
            self.maximum,
            self.consecutive,
            self.unavailable,
            self.gaps,
            self.cleared,
        )


def _side_sign(side: str) -> int:
    if side == "long":
        return 1
    if side == "short":
        return -1
    raise ValueError("dual-MTF reversal side must be long or short")


def _positive_integer(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("dual-MTF persistence must be an integer")
    if value < 1:
        raise ValueError("dual-MTF persistence must be positive")
    return value


def _require_chronology(rows: Sequence[DualMtfReversalObservation]) -> None:
    prior: int | None = None
    for row in rows:
        if prior is not None and row.decision_time_ms <= prior:
            raise ValueError("dual-MTF decisions must be strictly increasing")
        prior = row.decision_time_ms


def _validate_timestamp(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("dual-MTF decision time must be a nonnegative integer")
    if value % _MINUTE_MS:
        raise ValueError("dual-MTF decision time must align to a minute")


def _validate_prices(*values: float) -> None:
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError("dual-MTF prices must be positive and finite")
