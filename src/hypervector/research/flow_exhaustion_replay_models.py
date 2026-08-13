"""Typed contracts for report-only flow-exhaustion replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

from hypervector.research.shared_portfolio_models import Direction


FlowExitReason = Literal["liquidation", "stop", "target", "max_hold"]


@dataclass(frozen=True)
class FlowExhaustionReplayConfig:
    """Frozen shared-equity, risk, cost, and holding assumptions."""

    initial_equity_usd: float = 15_000.0
    risk_fraction: float = 0.0025
    maximum_margin_fraction: float = 0.10
    leverage: float = 5.0
    round_trip_cost_bps: float = 13.0
    fee_round_trip_bps: float = 9.0
    minimum_target_bps: float = 26.0
    maximum_hold_minutes: int = 30

    def __post_init__(self) -> None:
        for name in (
            "initial_equity_usd",
            "risk_fraction",
            "maximum_margin_fraction",
            "leverage",
            "round_trip_cost_bps",
            "minimum_target_bps",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if self.risk_fraction > 1.0 or self.maximum_margin_fraction > 1.0:
            raise ValueError("risk and margin fractions must not exceed one")
        if not 0.0 <= self.fee_round_trip_bps <= self.round_trip_cost_bps:
            raise ValueError("fee cost must be within total round-trip cost")
        if self.maximum_hold_minutes != 30:
            raise ValueError("flow-exhaustion maximum hold must equal 30 minutes")

    @property
    def fee_rate_per_side(self) -> float:
        """Return the frozen per-side taker fee rate."""
        return self.fee_round_trip_bps / 2.0 / 10_000.0

    @property
    def slippage_bps_per_side(self) -> float:
        """Return residual per-side slippage after explicit fees."""
        return (self.round_trip_cost_bps - self.fee_round_trip_bps) / 2.0


@dataclass(frozen=True)
class FlowExhaustionTrade:
    """One complete source-equity-normalized venue-path outcome."""

    trade_id: str
    symbol: str
    direction: Direction
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    liquidation_price: float
    quantity: float
    notional_usd: float
    isolated_margin_usd: float
    risk_budget_usd: float
    gross_pnl_usd: float
    entry_fee_usd: float
    exit_fee_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    net_pnl_usd: float
    scaled_net_pnl_usd: float
    exit_reason: FlowExitReason
    same_minute_ambiguous: bool


@dataclass(frozen=True)
class FlowExhaustionRejection:
    """One signal withheld from the report-only portfolio with exact reason."""

    symbol: str
    signal_time_utc: str
    side: str
    reason: str


@dataclass(frozen=True)
class FlowExhaustionReplayReport:
    """Shared-portfolio economics and complete accepted/rejected identities."""

    initial_equity_usd: float
    final_equity_usd: float
    net_pnl_usd: float
    return_pct: float
    completed_trades: int
    wins: int
    losses: int
    profit_factor: float | None
    maximum_drawdown_pct: float
    maximum_concurrent_positions: int
    total_fees_usd: float
    funding_cashflow_usd: float
    liquidations: int
    trades: tuple[FlowExhaustionTrade, ...]
    rejections: tuple[FlowExhaustionRejection, ...]
    report_only: bool = True
    execution_authority: str = "none"
    place_attempted: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible report representation."""
        return asdict(self)
