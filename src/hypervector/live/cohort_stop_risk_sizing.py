"""Optional stop-loss allowance in dollars and/or equity, excluding unbounded gaps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypervector.live.cohort_execution_plan import BoundExecutionPlan

BPS_PER_UNIT = 10_000.0
MAXIMUM_LOSS_FRACTION_OF_EQUITY_CEILING = 0.05
_BUDGET_KEYS = frozenset(
    {"maximum_loss_usd", "maximum_loss_fraction_of_equity", "cost_buffer_bps"}
)
_FRACTION_PAYLOAD_KEYS = (
    "maximum_loss_fraction_of_equity",
    "account_value_usd",
    "effective_maximum_loss_usd",
)


class StopRiskAccountValueError(ValueError):
    """An equity-fraction budget cannot be priced without a usable account value."""


@dataclass(frozen=True)
class StopRiskBudget:
    """User-configurable estimated stop loss including a declared cost allowance.

    A budget declares a dollar cap, an equity fraction, or both; the effective
    cap is the smaller one, with the fraction applied to the account value the
    entry sizing path used for that entry.
    """

    maximum_loss_usd: float | None
    cost_buffer_bps: float
    maximum_loss_fraction_of_equity: float | None = None

    def __post_init__(self) -> None:
        """Reject implicit, nonfinite or malformed loss allowances."""
        if (
            self.maximum_loss_usd is None
            and self.maximum_loss_fraction_of_equity is None
        ):
            raise ValueError(
                "stop_risk_budget requires maximum_loss_usd and/or "
                "maximum_loss_fraction_of_equity"
            )
        if self.maximum_loss_usd is not None:
            _positive(self.maximum_loss_usd, "maximum_loss_usd")
            object.__setattr__(self, "maximum_loss_usd", float(self.maximum_loss_usd))
        fraction = self.maximum_loss_fraction_of_equity
        if fraction is not None:
            _positive(fraction, "maximum_loss_fraction_of_equity")
            if fraction > MAXIMUM_LOSS_FRACTION_OF_EQUITY_CEILING:
                raise ValueError("maximum_loss_fraction_of_equity must be in (0, 0.05]")
            object.__setattr__(self, "maximum_loss_fraction_of_equity", float(fraction))
        if (
            isinstance(self.cost_buffer_bps, bool)
            or not isinstance(self.cost_buffer_bps, (int, float))
            or not math.isfinite(self.cost_buffer_bps)
        ):
            raise ValueError("cost_buffer_bps must be finite numeric")
        if not 0 <= self.cost_buffer_bps < BPS_PER_UNIT:
            raise ValueError("cost_buffer_bps must be in [0, 10000)")
        object.__setattr__(self, "cost_buffer_bps", float(self.cost_buffer_bps))

    @classmethod
    def from_payload(cls, value: object) -> StopRiskBudget | None:
        """Parse an explicit optional contract without inventing defaults."""
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise ValueError("stop_risk_budget must be a table")
        unknown = sorted(str(key) for key in value if key not in _BUDGET_KEYS)
        if unknown:
            raise ValueError(
                f"stop_risk_budget has unknown key(s): {', '.join(unknown)}"
            )
        declared = [key for key in _BUDGET_KEYS if key in value]
        if "cost_buffer_bps" not in value or len(declared) < 2:
            raise ValueError(
                "stop_risk_budget requires cost_buffer_bps and maximum_loss_usd "
                "and/or maximum_loss_fraction_of_equity"
            )
        if any(
            isinstance(value[key], bool) or not isinstance(value[key], (int, float))
            for key in declared
        ):
            raise ValueError("stop_risk_budget fields must be numeric")
        maximum = value.get("maximum_loss_usd")
        fraction = value.get("maximum_loss_fraction_of_equity")
        return cls(
            None if maximum is None else float(maximum),
            float(value["cost_buffer_bps"]),
            None if fraction is None else float(fraction),
        )

    def as_payload(self) -> dict[str, float]:
        """Return only declared fields; a dollar-only budget keeps its legacy shape."""
        return {key: item for key, item in asdict(self).items() if item is not None}

    def effective_maximum_loss_usd(self, account_value_usd: float | None) -> float:
        """Return the smaller declared cap, pricing a fraction on the given equity."""
        fraction = self.maximum_loss_fraction_of_equity
        if fraction is None:
            return float(self.maximum_loss_usd)  # type: ignore[arg-type]
        if (
            isinstance(account_value_usd, bool)
            or not isinstance(account_value_usd, (int, float))
            or not math.isfinite(account_value_usd)
            or account_value_usd <= 0
        ):
            raise StopRiskAccountValueError(
                "equity-fraction stop budget requires a finite positive account value"
            )
        equity_cap = fraction * float(account_value_usd)
        if self.maximum_loss_usd is None:
            return equity_cap
        return min(self.maximum_loss_usd, equity_cap)


@dataclass(frozen=True)
class StopRiskSizing:
    """Auditable pre-order estimate, not a guarantee against market gaps."""

    original_notional_usd: float
    notional_usd: float
    quantity: float
    entry_bound: float
    stop_bound: float
    estimated_loss_usd: float
    maximum_loss_usd: float | None
    cost_buffer_bps: float
    maximum_loss_fraction_of_equity: float | None = None
    account_value_usd: float | None = None
    effective_maximum_loss_usd: float | None = None

    def as_payload(self) -> dict[str, float | None]:
        """Return non-secret values; equity fields appear only for fraction budgets."""
        payload = asdict(self)
        if self.maximum_loss_fraction_of_equity is None:
            for key in _FRACTION_PAYLOAD_KEYS:
                payload.pop(key)
        return payload


def size_for_stop_risk(
    *,
    plan: BoundExecutionPlan,
    budget: StopRiskBudget,
    mark_price: float,
    side: str,
    entry_slippage_fraction: float,
    original_notional_usd: float,
    account_value_usd: float | None = None,
) -> StopRiskSizing:
    """Cap notional for the modeled fill interval, including stop-clamp turning points.

    ``account_value_usd`` must be the equity the entry sizing path used for the
    planned notional; a fraction budget refuses to size without it.
    """
    maximum_loss = budget.effective_maximum_loss_usd(account_value_usd)
    _positive(mark_price, "mark_price")
    _positive(original_notional_usd, "original_notional_usd")
    if side not in {"long", "short"}:
        raise ValueError("stop-risk side must be long or short")
    slip = entry_slippage_fraction
    if isinstance(slip, bool) or not math.isfinite(slip) or not 0 <= slip < 1:
        raise ValueError("entry slippage fraction must be finite and in [0, 1)")
    entry, stop, loss_per_unit = _worst_loss(plan, budget, mark_price, slip, side)
    _positive(loss_per_unit, "estimated loss per unit")
    quantity = min(original_notional_usd / mark_price, maximum_loss / loss_per_unit)
    _positive(quantity, "risk-sized quantity")
    fraction = budget.maximum_loss_fraction_of_equity
    return StopRiskSizing(
        original_notional_usd,
        quantity * mark_price,
        quantity,
        entry,
        stop,
        quantity * loss_per_unit,
        budget.maximum_loss_usd,
        budget.cost_buffer_bps,
        fraction,
        None if fraction is None else float(account_value_usd),  # type: ignore[arg-type]
        None if fraction is None else maximum_loss,
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
    # The mark is always modeled; a fill more favorable than a structural anchor
    # falls back to the contract's minimum clamp inside plan.stop_price.
    points = [(p, plan.stop_price(entry_price=p, side=side)) for p in (mark, *prices)]
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
