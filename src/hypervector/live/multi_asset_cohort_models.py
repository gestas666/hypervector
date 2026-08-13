"""Typed shared-account and asset facts projected by cohort telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import math

from hypervector.live.cohort_execution_plan import BoundExecutionPlan


@dataclass(frozen=True)
class SharedAccountFacts:
    """Venue-authoritative totals common to every symbol reconciliation."""

    account_value_usd: float
    withdrawable_usd: float
    total_margin_used_usd: float
    total_notional_position_usd: float
    balance_source: str | None = None

    def __post_init__(self) -> None:
        """Reject negative or non-finite account totals."""
        for name, value in self.__dict__.items():
            if name == "balance_source":
                continue
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be nonnegative and finite")
        if self.balance_source not in {
            None,
            "perp_clearinghouse_state",
            "spot_clearinghouse_state",
        }:
            raise ValueError("balance_source is unsupported")


@dataclass(frozen=True)
class AssetCohortSnapshot:
    """Latest backend state for one symbol in the shared portfolio."""

    symbol: str
    state: str
    position_size_signed: float
    entry_oid: int | None
    stop_oid: int | None
    last_fault: str | None
    mark_price: float | None = None
    entry_price: float | None = None
    liquidation_price: float | None = None
    margin_used_usd: float = 0.0
    position_value_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    leverage: int | None = None
    target_oid: int | None = None
    target_price: float | None = None
    execution_plan: BoundExecutionPlan | None = None
    market_reference_price: float | None = None

    @property
    def position_side(self) -> str | None:
        """Return direction from the venue-backed signed position size."""
        if self.position_size_signed > 0.0:
            return "long"
        if self.position_size_signed < 0.0:
            return "short"
        return None

    def as_payload(self) -> dict[str, object]:
        """Return one JSON-safe TUI projection."""
        return {
            "symbol": self.symbol,
            "state": self.state,
            "direction_capability": ["long", "short"],
            "position_size_signed": self.position_size_signed,
            "position_side": self.position_side,
            "entry_oid": self.entry_oid,
            "stop_oid": self.stop_oid,
            "target_oid": self.target_oid,
            "target_price": self.target_price,
            "execution_plan": (
                self.execution_plan.as_payload()
                if self.execution_plan is not None
                else None
            ),
            "last_fault": self.last_fault,
            "mark_price": self.mark_price,
            "market_reference_price": self.market_reference_price,
            "mark_price_source": self.mark_price_source,
            "entry_price": self.entry_price,
            "liquidation_price": self.liquidation_price,
            "liquidation_distance_pct": self.liquidation_distance_pct,
            "margin_used_usd": self.margin_used_usd,
            "position_value_usd": self.position_value_usd,
            "unrealized_pnl_usd": self.unrealized_pnl_usd,
            "leverage": self.leverage,
        }

    @property
    def liquidation_distance_pct(self) -> float | None:
        """Return absolute venue liquidation distance from the current mark."""
        if self.mark_price is None or self.liquidation_price is None:
            return None
        return abs(self.liquidation_price - self.mark_price) / self.mark_price * 100.0

    @property
    def mark_price_source(self) -> str:
        """Identify whether mark and position economics share one venue read."""
        if self.position_size_signed != 0.0 and self.position_value_usd > 0.0:
            return "venue_position_value_div_size"
        return "market_reference"
