"""Optional dollar stop-loss allowance, explicitly excluding unbounded gaps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
from typing import TYPE_CHECKING

from hypervector.live.cohort_execution_plan_validation import CohortExecutionPlanError

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import BoundExecutionPlan

BPS_PER_UNIT = 10_000.0


@dataclass(frozen=True)
class StopRiskBudget:
    """User-configurable estimated stop loss including a declared cost allowance."""

    maximum_loss_usd: float
    cost_buffer_bps: float

    def __post_init__(self) -> None:
        """Reject implicit, nonfinite or malformed loss allowances."""
        _positive(self.maximum_loss_usd, "maximum_loss_usd")
        if (
            isinstance(self.cost_buffer_bps, bool)
            or not isinstance(self.cost_buffer_bps, (int, float))
            or not math.isfinite(self.cost_buffer_bps)
        ):
            raise ValueError("cost_buffer_bps must be finite numeric")
        if not 0 <= self.cost_buffer_bps < BPS_PER_UNIT:
            raise ValueError("cost_buffer_bps must be in [0, 10000)")
        object.__setattr__(self, "maximum_loss_usd", float(self.maximum_loss_usd))
        object.__setattr__(self, "cost_buffer_bps", float(self.cost_buffer_bps))

    @classmethod
    def from_payload(cls, value: object) -> StopRiskBudget | None:
        """Parse an explicit optional contract without inventing defaults."""
        if value is None:
            return None
        if not isinstance(value, Mapping) or set(value) != {
            "maximum_loss_usd",
            "cost_buffer_bps",
        }:
            raise ValueError(
                "stop_risk_budget requires maximum_loss_usd and cost_buffer_bps"
            )
        maximum, buffer = value["maximum_loss_usd"], value["cost_buffer_bps"]
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float))
            for v in (maximum, buffer)
        ):
            raise ValueError("stop_risk_budget fields must be numeric")
        return cls(float(maximum), float(buffer))


@dataclass(frozen=True)
class StopRiskSizing:
    """Auditable pre-order estimate, not a guarantee against market gaps."""

    original_notional_usd: float
    notional_usd: float
    quantity: float
    entry_bound: float
    stop_bound: float
    estimated_loss_usd: float
    maximum_loss_usd: float
    cost_buffer_bps: float

    def as_payload(self) -> dict[str, float]:
        """Return non-secret values for durable pre-order telemetry."""
        return asdict(self)


def size_for_stop_risk(
    *,
    plan: BoundExecutionPlan,
    budget: StopRiskBudget,
    mark_price: float,
    side: str,
    entry_slippage_fraction: float,
    original_notional_usd: float,
) -> StopRiskSizing:
    """Cap notional for the modeled fill interval, including stop-clamp turning points."""
    _positive(mark_price, "mark_price")
    _positive(original_notional_usd, "original_notional_usd")
    if side not in {"long", "short"}:
        raise ValueError("stop-risk side must be long or short")
    slip = entry_slippage_fraction
    if isinstance(slip, bool) or not math.isfinite(slip) or not 0 <= slip < 1:
        raise ValueError("entry slippage fraction must be finite and in [0, 1)")
    entry, stop, loss_per_unit = _worst_loss(plan, budget, mark_price, slip, side)
    _positive(loss_per_unit, "estimated loss per unit")
    quantity = min(
        original_notional_usd / mark_price, budget.maximum_loss_usd / loss_per_unit
    )
    _positive(quantity, "risk-sized quantity")
    return StopRiskSizing(
        original_notional_usd,
        quantity * mark_price,
        quantity,
        entry,
        stop,
        quantity * loss_per_unit,
        budget.maximum_loss_usd,
        budget.cost_buffer_bps,
    )


def _worst_loss(
    plan: BoundExecutionPlan,
    budget: StopRiskBudget,
    mark: float,
    slip: float,
    side: str,
) -> tuple[float, float, float]:
    low, high = mark * (1 - slip), mark * (1 + slip)
    _positive(low, "lower fill bound")
    _positive(high, "upper fill bound")
    prices = [low, high]
    if plan.stop_policy == "structural_clamped_bps":
        sign = -1 if side == "long" else 1
        if (
            plan.stop_anchor is None
            or plan.minimum_stop_bps is None
            or plan.maximum_stop_bps is None
        ):
            raise ValueError("structural risk sizing requires a complete bound stop")
        for bps in (plan.minimum_stop_bps, plan.maximum_stop_bps):
            denominator = 1 + sign * bps / BPS_PER_UNIT
            if denominator <= 0:
                continue
            boundary = plan.stop_anchor / denominator
            if low < boundary < high:
                prices.append(boundary)
    # The plan must resolve a stop at the mark itself; an anchor that is not adverse
    # there cannot size an order and is refused before any submission.
    points = [(mark, plan.stop_price(entry_price=mark, side=side))]
    for price in prices:
        try:
            points.append((price, plan.stop_price(entry_price=price, side=side)))
        except CohortExecutionPlanError:
            # A modeled fill more favorable than the structural anchor has no
            # bound stop and cannot be the worst loss; post-fill protection
            # rejects such a fill independently, so it must not fault the entry.
            continue
    estimates = [
        (p, s, abs(p - s) + p * budget.cost_buffer_bps / BPS_PER_UNIT)
        for p, s in points
    ]
    return max(estimates, key=lambda point: point[2])


def _positive(value: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be finite and positive")
