"""Research-only sizing contract for BTC maker replay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from hypervector.research.maker_replay_models import MakerReplayConfig
from hypervector.strategies.hypervelocity_contract import HypervelocityAllocation


class MakerReplayPositionContract(Protocol):
    """Structural contract consumed by maker order and trade handlers."""

    leverage: float

    @property
    def target_price_fraction(self) -> float:
        """Return the unlevered target move."""
        ...

    def allocate(self, equity: float) -> HypervelocityAllocation:
        """Return margin and notional for current equity."""
        ...


@dataclass(frozen=True)
class ResearchMakerContract:
    """Explicit research sizing variant that cannot alter runtime authority."""

    margin_fraction: float
    leverage: float
    target_margin_pct: float

    @property
    def target_price_fraction(self) -> float:
        """Return the unlevered price move for the margin-return target."""
        return self.target_margin_pct / self.leverage / 100.0

    def allocate(self, equity: float) -> HypervelocityAllocation:
        """Allocate the configured fraction of positive research equity."""
        equity_value = float(equity)
        if equity_value <= 0.0:
            raise ValueError(f"equity must be positive, got {equity!r}")
        margin = equity_value * self.margin_fraction
        return HypervelocityAllocation(margin=margin, notional=margin * self.leverage)


def maker_replay_contract(config: MakerReplayConfig) -> ResearchMakerContract:
    """Build the research sizing contract for one validated replay config."""
    return ResearchMakerContract(
        margin_fraction=config.margin_fraction,
        leverage=config.leverage,
        target_margin_pct=config.target_margin_pct,
    )


def target_price_for_entry(
    contract: MakerReplayPositionContract,
    *,
    entry_price: float,
    direction: Literal["long", "short"],
    target_price_points: float | None = None,
) -> float:
    """Return the first target reached by relative or absolute price movement."""
    if entry_price <= 0.0:
        raise ValueError("entry_price must be positive")
    if direction not in {"long", "short"}:
        raise ValueError("direction must be long or short")
    price_move = entry_price * contract.target_price_fraction
    if target_price_points is not None:
        if target_price_points <= 0.0:
            raise ValueError("target_price_points must be positive")
        price_move = min(price_move, target_price_points)
    return entry_price + price_move if direction == "long" else entry_price - price_move
