"""Fixed, observed Hypervelocity baseline contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from hypervector.regime.models import BreakoutDirection, PrimaryRegime

EntryDirection = Literal["long", "short"]

_MARGIN_FRACTION = 0.70
_LEVERAGE = 40.0
_TARGET_MARGIN_PCT = 8.0


@dataclass(frozen=True)
class HypervelocityAllocation:
    """Margin and notional allocated for one candidate trade."""

    margin: float
    notional: float


@dataclass(frozen=True)
class HypervelocityContract:
    """Immutable facts of the faithful BTC Hypervelocity baseline."""

    margin_fraction: float = _MARGIN_FRACTION
    leverage: float = _LEVERAGE
    target_margin_pct: float = _TARGET_MARGIN_PCT
    order_type: str = "limit"
    time_in_force: str = "post_only"

    def __post_init__(self) -> None:
        if self.margin_fraction != _MARGIN_FRACTION:
            raise ValueError("margin_fraction must be 0.70 for the faithful baseline")
        if self.leverage != _LEVERAGE:
            raise ValueError("leverage must be 40.0 for the faithful baseline")
        if self.target_margin_pct != _TARGET_MARGIN_PCT:
            raise ValueError("target_margin_pct must be 8.0 for the faithful baseline")
        if self.order_type != "limit" or self.time_in_force != "post_only":
            raise ValueError("faithful baseline execution must be limit post_only")

    @property
    def target_price_fraction(self) -> float:
        """Return the unlevered price move required for the margin target."""
        return self.target_margin_pct / self.leverage / 100.0

    def allocate(self, equity: float) -> HypervelocityAllocation:
        """Allocate 70% of positive equity as margin at 40x leverage."""
        equity_value = float(equity)
        if equity_value <= 0.0:
            raise ValueError(f"equity must be positive, got {equity!r}")
        margin = equity_value * self.margin_fraction
        return HypervelocityAllocation(
            margin=margin,
            notional=margin * self.leverage,
        )


def entry_direction_for(
    primary: PrimaryRegime,
    breakout: BreakoutDirection | None = None,
) -> EntryDirection | None:
    """Map an authoritative regime event to an allowed entry direction."""
    if primary is PrimaryRegime.TREND_UP:
        return "long"
    if primary is PrimaryRegime.TREND_DOWN:
        return "short"
    if primary is PrimaryRegime.BREAKOUT:
        if breakout is BreakoutDirection.UPWARD:
            return "long"
        if breakout is BreakoutDirection.DOWNWARD:
            return "short"
    return None

