"""Typed contracts for one-minute-path low-timeframe strategy replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

from hypervector.research.shared_portfolio_models import Direction

LowTfExitReason = Literal[
    "liquidation",
    "stop",
    "target",
    "close_invalidation",
    "rsi_reversal",
    "rsi_divergence",
    "ema_alignment",
    "pmarp_opposite_extreme",
    "max_hold",
    "end_of_data",
]


@dataclass(frozen=True)
class LowTfReplayConfig:
    """Risk, venue, cost, and cooldown assumptions for one strategy cell."""

    initial_equity: float = 15_000.0
    risk_fraction: float = 0.005
    maximum_margin_fraction: float = 0.70
    leverage: float = 5.0
    venue_max_leverage: float = 40.0
    round_trip_cost_bps: float = 13.0
    fee_round_trip_bps: float = 9.0
    liquidation_penalty_rate: float = 0.01
    reentry_cooldown_bars: int = 1

    def __post_init__(self) -> None:
        """Reject incoherent portfolio, leverage, and cost assumptions."""
        _positive(self.initial_equity, "initial_equity")
        _fraction(self.risk_fraction, "risk_fraction")
        _fraction(self.maximum_margin_fraction, "maximum_margin_fraction")
        _positive(self.leverage, "leverage")
        _positive(self.venue_max_leverage, "venue_max_leverage")
        if self.leverage > self.venue_max_leverage:
            raise ValueError("leverage must not exceed venue_max_leverage")
        _positive(self.round_trip_cost_bps, "round_trip_cost_bps")
        _nonnegative(self.fee_round_trip_bps, "fee_round_trip_bps")
        if self.fee_round_trip_bps > self.round_trip_cost_bps:
            raise ValueError("fee cost cannot exceed total round-trip cost")
        _rate(self.liquidation_penalty_rate, "liquidation_penalty_rate")
        _nonnegative_integer(self.reentry_cooldown_bars, "reentry_cooldown_bars")

    @property
    def fee_rate_per_side(self) -> float:
        """Return half the declared round-trip fee in decimal price terms."""
        return self.fee_round_trip_bps / 2.0 / 10_000.0

    @property
    def slippage_bps_per_side(self) -> float:
        """Return residual all-in cost assigned to each execution side."""
        residual = self.round_trip_cost_bps - self.fee_round_trip_bps
        return residual / 2.0


@dataclass(frozen=True)
class LowTfReplayTrade:
    """One complete flat-to-flat trade from a frozen strategy cell."""

    symbol: str
    family: str
    exit_variant: str
    direction: Direction
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float | None
    liquidation_price: float
    quantity: float
    risk_budget_usd: float
    isolated_margin_usd: float
    gross_pnl_usd: float
    entry_fee_usd: float
    exit_fee_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalty_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    exit_reason: LowTfExitReason
    same_minute_ambiguous: bool


@dataclass(frozen=True)
class LowTfReplayRejection:
    """One unfilled signal and its explicit causal reason."""

    signal_time_utc: str
    symbol: str
    family: str
    exit_variant: str
    reason: str


@dataclass(frozen=True)
class LowTfReplayReport:
    """Aggregate evidence for exactly one asset/family/side/variant cell."""

    initial_equity: float
    final_equity: float
    gross_pnl_usd: float
    total_fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalties_usd: float
    net_pnl_usd: float
    completed_trades: int
    wins: int
    losses: int
    profit_factor: float | None
    maximum_drawdown_pct: float
    liquidations: int
    same_minute_ambiguities: int
    trades: tuple[LowTfReplayTrade, ...]
    rejections: tuple[LowTfReplayRejection, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible evidence record."""
        return asdict(self)


def _finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")


def _positive(value: float, label: str) -> None:
    _finite(value, label)
    if value <= 0.0:
        raise ValueError(f"{label} must be positive")


def _nonnegative(value: float, label: str) -> None:
    _finite(value, label)
    if value < 0.0:
        raise ValueError(f"{label} must be non-negative")


def _fraction(value: float, label: str) -> None:
    _positive(value, label)
    if value > 1.0:
        raise ValueError(f"{label} must not exceed one")


def _rate(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value >= 1.0:
        raise ValueError(f"{label} must be below one")


def _nonnegative_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
