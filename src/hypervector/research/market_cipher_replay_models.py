"""Typed contracts for causal shared-capital Market Cipher replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Literal

from hypervector.research.shared_portfolio_models import Direction

ExitVariant = Literal["all_at_2r_control", "staged_25_50_trail"]
ReplayExitReason = Literal[
    "target_1r",
    "target_reward_risk",
    "stop",
    "liquidation",
    "opposite_wave_cross",
    "max_hold",
    "end_of_data",
]


@dataclass(frozen=True)
class MarketCipherReplayConfig:
    """Frozen risk, execution, and staged-exit assumptions."""

    initial_equity: float = 15_000.0
    risk_fraction: float = 0.005
    maximum_portfolio_risk_fraction: float = 0.02
    maximum_concurrent_positions: int = 3
    maximum_signal_risk_multiplier: float = 1.0
    entry_delay_bars: int = 1
    leverage: float = 5.0
    venue_max_leverage_by_symbol: tuple[tuple[str, float], ...] = (
        ("BTC", 40.0),
        ("ETH", 25.0),
        ("SOL", 20.0),
        ("HYPE", 10.0),
    )
    exit_variant: ExitVariant = "all_at_2r_control"
    minimum_stop_bps: float = 20.0
    maximum_stop_bps: float = 50.0
    target_r_multiple: float = 2.0
    maximum_hold_bars: int = 12
    entry_fee_rate: float = 0.00045
    target_fee_rate: float = 0.00015
    market_exit_fee_rate: float = 0.00045
    liquidation_penalty_rate: float = 0.01
    funding_rate_multiplier: float = 1.0
    entry_slippage_bps: float = 2.0
    market_exit_slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        """Reject invalid or internally inconsistent replay settings."""
        _positive(self.initial_equity, "initial_equity")
        _fraction(self.risk_fraction, "risk_fraction")
        _fraction(
            self.maximum_portfolio_risk_fraction,
            "maximum_portfolio_risk_fraction",
        )
        _positive_integer(
            self.maximum_concurrent_positions,
            "maximum_concurrent_positions",
        )
        _positive_integer(self.entry_delay_bars, "entry_delay_bars")
        _positive(
            self.maximum_signal_risk_multiplier,
            "maximum_signal_risk_multiplier",
        )
        configured = (
            self.risk_fraction
            * self.maximum_concurrent_positions
            * self.maximum_signal_risk_multiplier
        )
        if configured > self.maximum_portfolio_risk_fraction:
            raise ValueError("configured portfolio risk exceeds frozen cap")
        self._validate_leverage_and_stops()
        self._validate_costs()
        if self.exit_variant not in {
            "all_at_2r_control",
            "staged_25_50_trail",
        }:
            raise ValueError("unsupported Market Cipher exit variant")

    def _validate_leverage_and_stops(self) -> None:
        _positive(self.leverage, "leverage")
        symbols = [symbol for symbol, _ in self.venue_max_leverage_by_symbol]
        if len(symbols) != len(set(symbols)) or any(not symbol for symbol in symbols):
            raise ValueError("venue leverage symbols must be unique and non-empty")
        for symbol, maximum in self.venue_max_leverage_by_symbol:
            _positive(maximum, f"{symbol} venue maximum leverage")
        _positive(self.minimum_stop_bps, "minimum_stop_bps")
        _positive(self.maximum_stop_bps, "maximum_stop_bps")
        if self.minimum_stop_bps > self.maximum_stop_bps:
            raise ValueError("minimum_stop_bps must not exceed maximum_stop_bps")
        _positive(self.target_r_multiple, "target_r_multiple")
        _positive_integer(self.maximum_hold_bars, "maximum_hold_bars")

    def venue_max_leverage_for(self, symbol: str) -> float:
        """Return the configured Hyperliquid tier or reject an unknown asset."""
        tiers = dict(self.venue_max_leverage_by_symbol)
        if symbol not in tiers:
            raise ValueError(f"missing venue maximum leverage for {symbol}")
        maximum = tiers[symbol]
        if self.leverage > maximum:
            raise ValueError(
                f"leverage {self.leverage} exceeds {symbol} venue maximum {maximum}"
            )
        return maximum

    def _validate_costs(self) -> None:
        _nonnegative(self.funding_rate_multiplier, "funding_rate_multiplier")
        for name in (
            "entry_fee_rate",
            "target_fee_rate",
            "market_exit_fee_rate",
            "liquidation_penalty_rate",
        ):
            _rate(float(getattr(self, name)), name)
        for name in ("entry_slippage_bps", "market_exit_slippage_bps"):
            _nonnegative(float(getattr(self, name)), name)


@dataclass(frozen=True)
class ReplayExitLeg:
    """One realized reduction of an initially opened position."""

    time_utc: str
    reason: ReplayExitReason
    price: float
    quantity: float
    fraction_of_initial: float
    gross_pnl_usd: float
    fee_usd: float
    liquidation_penalty_usd: float


@dataclass(frozen=True)
class MarketCipherReplayTrade:
    """One flat-to-flat trade, including every partial exit."""

    candidate: str
    signal_score: float
    symbol: str
    direction: Direction
    signal_time_utc: str
    entry_time_utc: str
    exit_time_utc: str
    entry_price: float
    exit_price: float
    stop_price: float
    stop_distance_bps: float
    liquidation_price: float
    risk_budget_usd: float
    initial_quantity: float
    isolated_margin_usd: float
    gross_pnl_usd: float
    fees_usd: float
    funding_cashflow_usd: float
    liquidation_penalty_usd: float
    net_pnl_usd: float
    equity_before_usd: float
    equity_after_usd: float
    exit_reason: ReplayExitReason
    exit_legs: tuple[ReplayExitLeg, ...]


@dataclass(frozen=True)
class ReplayRejection:
    """One signal rejected by an explicit portfolio or data constraint."""

    signal_time_utc: str
    symbol: str
    candidate: str
    reason: str


@dataclass(frozen=True)
class MarketCipherReplayReport:
    """Auditable aggregate for one shared funded portfolio."""

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
    maximum_concurrent_positions: int
    trades: tuple[MarketCipherReplayTrade, ...]
    rejections: tuple[ReplayRejection, ...]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible report."""
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
        raise ValueError(f"{label} must not exceed 1")


def _rate(value: float, label: str) -> None:
    _nonnegative(value, label)
    if value >= 1.0:
        raise ValueError(f"{label} must be below 1")


def _positive_integer(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
