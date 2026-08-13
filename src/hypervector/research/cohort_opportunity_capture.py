"""Report-only opportunity capture metrics for causal directional paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import median

from hypervector.research.cohort_forward_paths import DirectionalPath

DEFAULT_ESTIMATED_ROUND_TRIP_FRICTION_BPS = 13.0
DEFAULT_ROBUST_GROSS_MOVE_BPS = 26.0


@dataclass(frozen=True)
class OpportunityHurdles:
    """Fixed gross-path hurdles used for non-executable diagnostics."""

    estimated_round_trip_friction_bps: float
    robust_gross_move_bps: float

    def as_payload(self) -> dict[str, float]:
        """Return the explicit hurdle assumptions for checkpoint telemetry."""
        return {
            "estimated_round_trip_friction": self.estimated_round_trip_friction_bps,
            "robust_gross_move": self.robust_gross_move_bps,
        }


def opportunity_hurdles(
    estimated_round_trip_friction_bps: float,
    robust_gross_move_bps: float,
) -> OpportunityHurdles:
    """Validate fixed path hurdles without selecting them from outcomes."""
    values = (estimated_round_trip_friction_bps, robust_gross_move_bps)
    if not all(isfinite(value) and value > 0.0 for value in values):
        raise ValueError("opportunity hurdles must be finite and positive")
    if robust_gross_move_bps < estimated_round_trip_friction_bps:
        raise ValueError("robust gross move must not be below estimated friction")
    return OpportunityHurdles(*values)


def summarize_path_opportunities(
    outcomes: Sequence[DirectionalPath],
    hurdles: OpportunityHurdles,
) -> dict[str, object]:
    """Quantify causal gross paths without assuming fills, exits, or PnL."""
    resolved = len(outcomes)
    friction = hurdles.estimated_round_trip_friction_bps
    robust = hurdles.robust_gross_move_bps
    cost_clearing = [
        value for value in outcomes if value.favorable_excursion_bps >= friction
    ]
    robust_paths = [
        value for value in outcomes if value.favorable_excursion_bps >= robust
    ]
    cost_closes = [
        value for value in outcomes if value.directional_close_return_bps >= friction
    ]
    reversals = [
        value
        for value in cost_clearing
        if value.directional_close_return_bps < friction
    ]
    close_after_cost = [
        value.directional_close_return_bps - friction for value in outcomes
    ]
    return {
        "resolved": resolved,
        "cost_clearing_mfe_count": len(cost_clearing),
        "cost_clearing_mfe_rate": _rate(len(cost_clearing), resolved),
        "robust_mfe_count": len(robust_paths),
        "robust_mfe_rate": _rate(len(robust_paths), resolved),
        "cost_clearing_close_count": len(cost_closes),
        "cost_clearing_close_rate": _rate(len(cost_closes), resolved),
        "failed_to_clear_cost_count": resolved - len(cost_clearing),
        "reversed_after_cost_clear_count": len(reversals),
        "mean_close_after_estimated_friction_bps": _mean(close_after_cost),
        "median_close_after_estimated_friction_bps": _median(close_after_cost),
        "minimum_close_after_estimated_friction_bps": _minimum(close_after_cost),
        "maximum_close_after_estimated_friction_bps": _maximum(close_after_cost),
        "mean_excluding_largest_close_after_estimated_friction_bps": (
            _mean_excluding_largest(close_after_cost)
        ),
    }


def _rate(count: int, total: int) -> float | None:
    return count / total if total else None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return float(median(values)) if values else None


def _minimum(values: Sequence[float]) -> float | None:
    return min(values) if values else None


def _maximum(values: Sequence[float]) -> float | None:
    return max(values) if values else None


def _mean_excluding_largest(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    return (sum(values) - max(values)) / (len(values) - 1)
